"""Create the five EquipmentDesk tables and timestamp triggers.

Revision ID: 0001_initial_schema
Revises: None
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def created_at():
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def updated_at():
    return sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False),
        created_at(),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.CheckConstraint("length(trim(username)) > 0", name="username_not_blank"),
        sa.CheckConstraint("length(trim(full_name)) > 0", name="full_name_not_blank"),
    )
    op.create_table(
        "equipment",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="AVAILABLE"),
        sa.Column("location", sa.String(200)),
        created_at(), updated_at(),
        sa.UniqueConstraint("code", name="uq_equipment_code"),
        sa.CheckConstraint("status IN ('AVAILABLE', 'BORROWED', 'MAINTENANCE')", name="valid_status"),
        sa.CheckConstraint("length(trim(code)) > 0", name="code_not_blank"),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        sa.CheckConstraint("length(trim(category)) > 0", name="category_not_blank"),
    )
    op.create_table(
        "loans",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("loan_code", sa.String(80), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("loan_date", sa.Date(), nullable=False),
        sa.Column("expected_return_date", sa.Date(), nullable=False),
        sa.Column("actual_return_date", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default="BORROWED"),
        sa.Column("note", sa.Text()),
        created_at(), updated_at(),
        sa.UniqueConstraint("loan_code", name="uq_loans_loan_code"),
        sa.CheckConstraint("length(trim(loan_code)) > 0", name="loan_code_not_blank"),
        sa.CheckConstraint("status IN ('BORROWED', 'RETURNED')", name="valid_status"),
        sa.CheckConstraint("expected_return_date >= loan_date", name="expected_return_date"),
        sa.CheckConstraint("actual_return_date IS NULL OR actual_return_date >= loan_date", name="actual_return_date"),
        sa.CheckConstraint("(status = 'BORROWED' AND actual_return_date IS NULL) OR "
                           "(status = 'RETURNED' AND actual_return_date IS NOT NULL)", name="return_state"),
    )
    op.create_index("ix_loans_user_id", "loans", ["user_id"])
    op.create_table(
        "loan_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("loan_id", sa.BigInteger(), sa.ForeignKey("loans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("equipment_id", sa.BigInteger(), sa.ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("condition_before", sa.Text(), nullable=False),
        sa.Column("condition_after", sa.Text()),
        sa.UniqueConstraint("loan_id", "equipment_id", name="uq_loan_items_loan_equipment"),
        sa.CheckConstraint("length(trim(condition_before)) > 0", name="condition_before_not_blank"),
    )
    op.create_index("ix_loan_items_equipment_id", "loan_items", ["equipment_id"])
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("loan_id", sa.BigInteger(), sa.ForeignKey("loans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        created_at(),
        sa.UniqueConstraint("relative_path", name="uq_attachments_relative_path"),
        sa.CheckConstraint("size >= 0", name="nonnegative_size"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="valid_sha256"),
        sa.CheckConstraint("length(trim(original_name)) > 0", name="original_name_not_blank"),
        sa.CheckConstraint("length(trim(content_type)) > 0", name="content_type_not_blank"),
        sa.CheckConstraint("length(relative_path) > 0 AND relative_path !~ '^/' "
                           "AND relative_path !~ '(^|/)[.]{1,2}(/|$)' "
                           "AND position(chr(92) in relative_path) = 0 "
                           "AND position(':' in relative_path) = 0", name="relative_path"),
    )
    op.create_index("ix_attachments_loan_id", "attachments", ["loan_id"])
    # SQL updates outside the ORM must also maintain updated_at.
    op.execute("""
        CREATE FUNCTION equipmentdesk_touch_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$
    """)
    for table in ("equipment", "loans"):
        op.execute(f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION equipmentdesk_touch_updated_at()")


def downgrade():
    for table in ("loans", "equipment"):
        op.execute(f"DROP TRIGGER trg_{table}_updated_at ON {table}")
    op.execute("DROP FUNCTION equipmentdesk_touch_updated_at()")
    op.drop_table("attachments")
    op.drop_table("loan_items")
    op.drop_table("loans")
    op.drop_table("equipment")
    op.drop_table("users")
