from datetime import date
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.exc import IntegrityError

from equipmentdesk.models import Attachment, Equipment, Loan, LoanItem, User

pytestmark = pytest.mark.postgresql


def records(database):
    user = User(username=uuid4().hex, password_hash="test-hash", full_name="Demo")
    equipment = Equipment(code=uuid4().hex, name="Laptop", category="Computer")
    loan = Loan(loan_code=uuid4().hex, user=user, loan_date=date(2026, 9, 24),
                expected_return_date=date(2026, 9, 25))
    item = LoanItem(loan=loan, equipment=equipment, condition_before="Good")
    attachment = Attachment(loan=loan, relative_path=f"loans/{uuid4()}.txt",
                            original_name="receipt.txt", content_type="text/plain", size=3, sha256="a" * 64)
    database.session.add_all([user, equipment, loan, item, attachment])
    database.session.flush()
    return user, equipment, loan, item, attachment


def test_migration_matches_models(database):
    with database.engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True, "compare_server_default": True})
        assert compare_metadata(context, database.metadata) == []
    assert set(sa.inspect(database.engine).get_table_names()) == {
        "users", "equipment", "loans", "loan_items", "attachments", "alembic_version"}


def test_relationships_defaults_and_uuid(database):
    user, equipment, loan, item, attachment = records(database)
    database.session.expire_all()
    assert loan.user == user and loan in user.loans
    assert item in loan.items and item in equipment.loan_items
    assert attachment in loan.attachments and attachment.loan == loan
    assert isinstance(attachment.id, UUID)
    assert equipment.status == "AVAILABLE" and loan.status == "BORROWED"
    assert user.created_at.tzinfo is not None
    assert equipment.updated_at.tzinfo is not None


@pytest.mark.parametrize("record, attribute, value", [
    (1, "status", "INVALID"),
    (2, "status", "OVERDUE"),
    (2, "expected_return_date", date(2026, 9, 23)),
    (2, "actual_return_date", date(2026, 9, 25)),
    (2, "status", "RETURNED"),
    (4, "size", -1),
    (4, "sha256", "bad"),
    (4, "relative_path", "../escape.txt"),
    (4, "relative_path", "/absolute.txt"),
    (4, "relative_path", "loans/../escape.txt"),
    (4, "loan_id", None),
    (4, "loan_id", 999999),
])
def test_database_rejects_invalid_values(database, record, attribute, value):
    row = records(database)[record]
    setattr(row, attribute, value)
    with pytest.raises(IntegrityError):
        database.session.flush()


@pytest.mark.parametrize("kind", ["username", "code", "loan_code", "loan_item", "path"])
def test_unique_constraints(database, kind):
    user, equipment, loan, item, attachment = records(database)
    duplicates = {
        "username": User(username=user.username, password_hash="hash", full_name="Duplicate"),
        "code": Equipment(code=equipment.code, name="Duplicate", category="Computer"),
        "loan_code": Loan(loan_code=loan.loan_code, user_id=user.id, loan_date=loan.loan_date,
                          expected_return_date=loan.expected_return_date),
        "loan_item": LoanItem(loan_id=loan.id, equipment_id=equipment.id, condition_before="Good"),
        "path": Attachment(loan_id=loan.id, relative_path=attachment.relative_path,
                           original_name="copy.txt", content_type="text/plain", size=0, sha256="a" * 64),
    }
    database.session.add(duplicates[kind])
    with pytest.raises(IntegrityError):
        database.session.flush()


def test_foreign_keys_preserve_loan_history(database):
    user, *_ = records(database)
    database.session.delete(user)
    with pytest.raises(IntegrityError):
        database.session.flush()


def test_return_dates_and_equipment_history(database):
    user, equipment, loan, *_ = records(database)
    loan.status = "RETURNED"
    loan.actual_return_date = date(2026, 9, 25)
    next_loan = Loan(loan_code=uuid4().hex, user=user, loan_date=date(2026, 9, 26),
                     expected_return_date=date(2026, 9, 27))
    database.session.add(LoanItem(loan=next_loan, equipment=equipment, condition_before="Good"))
    database.session.flush()
    assert len(equipment.loan_items) == 2


@pytest.mark.parametrize("table, index", [("equipment", 1), ("loans", 2)])
def test_sql_updates_refresh_timestamp(database, table, index):
    row = records(database)[index]
    # Trigger replaces explicit old values even for SQL written outside the ORM.
    result = database.session.execute(sa.text(
        f"UPDATE {table} SET updated_at = '2000-01-01T00:00:00Z' WHERE id = :id RETURNING updated_at"
    ), {"id": row.id}).scalar_one()
    assert result.year != 2000
