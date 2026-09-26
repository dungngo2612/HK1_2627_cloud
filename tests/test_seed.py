from hashlib import sha256
from io import BytesIO
from uuid import uuid4

import pytest
import sqlalchemy as sa
from PIL import Image
from pypdf import PdfReader

from equipmentdesk.extensions import db
from equipmentdesk.models import Attachment, Equipment, Loan, LoanItem, User
from equipmentdesk.services.attachments import download_bytes

pytestmark = pytest.mark.postgresql
DEMO_PASSWORD = "seed-demo-password-123"


def test_seed_command_twice_is_idempotent_and_preserves_edits(postgres_app, tmp_path):
    username = "seed-user-" + uuid4().hex
    root = tmp_path / "seed-storage"
    postgres_app.config["APP_STORAGE_ROOT"] = root
    runner = postgres_app.test_cli_runner()
    env = {"DEMO_USERNAME": username, "DEMO_PASSWORD": DEMO_PASSWORD}

    first = runner.invoke(args=["seed-demo-data"], env=env)
    assert first.exit_code == 0, first.output
    assert "20 thiết bị mới" in first.output
    assert "10 phiếu mới" in first.output
    assert "5 file mới" in first.output

    with postgres_app.app_context():
        user = db.session.scalar(sa.select(User).where(User.username == username))
        equipment = db.session.scalar(sa.select(Equipment).where(Equipment.code == "DEMO-EQ-001"))
        loan = db.session.scalar(sa.select(Loan).where(Loan.loan_code == "DEMO-LOAN-001"))
        user_id = user.id
        password_hash = user.password_hash
        user.full_name = "Tên do người dùng chỉnh sửa"
        equipment.description = "Mô tả chỉnh sửa thủ công"
        loan.note = "Ghi chú do người dùng chỉnh sửa"
        db.session.commit()

        loans = db.session.scalars(sa.select(Loan).where(Loan.loan_code.like("DEMO-LOAN-%"))).all()
        assert len(loans) == 10
        assert sum(loan.status == "BORROWED" for loan in loans) == 5
        assert sum(loan.status == "RETURNED" for loan in loans) == 5
        for item in db.session.scalars(sa.select(LoanItem).join(Loan)).all():
            if item.loan.loan_code.startswith("DEMO-LOAN-"):
                expected = "BORROWED" if item.loan.status == "BORROWED" else "AVAILABLE"
                assert item.equipment.status == expected

        attachments = db.session.scalars(sa.select(Attachment).join(Loan).where(
            Loan.loan_code.like("DEMO-LOAN-%"),
            Attachment.original_name.like("bien-ban-demo-%"),
        )).all()
        assert len(attachments) == 5
        verified_types = set()
        checksums = set()
        for attachment in attachments:
            data = download_bytes(attachment)
            assert len(data) == attachment.size
            assert sha256(data).hexdigest() == attachment.sha256
            checksums.add(attachment.sha256)
            verified_types.add(attachment.content_type)
            if attachment.content_type == "application/pdf":
                assert len(PdfReader(BytesIO(data), strict=True).pages) == 1
            else:
                with Image.open(BytesIO(data)) as image:
                    image.verify()
        assert verified_types == {"application/pdf", "image/png", "image/jpeg"}
        assert len(checksums) == 5

    second = runner.invoke(args=["seed-demo-data"], env=env)
    assert second.exit_code == 0, second.output
    assert "0 thiết bị mới" in second.output
    assert "0 phiếu mới" in second.output
    assert "0 file mới" in second.output

    with postgres_app.app_context():
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Equipment).where(
            Equipment.code.like("DEMO-EQ-%"))) == 20
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Loan).where(
            Loan.loan_code.like("DEMO-LOAN-%"))) == 10
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Attachment).join(Loan).where(
            Loan.loan_code.like("DEMO-LOAN-%"),
            Attachment.original_name.like("bien-ban-demo-%"))) == 5
        user = db.session.get(User, user_id)
        assert user.full_name == "Tên do người dùng chỉnh sửa"
        assert user.password_hash == password_hash
        assert db.session.scalar(sa.select(Equipment.description).where(
            Equipment.code == "DEMO-EQ-001")) == "Mô tả chỉnh sửa thủ công"
        assert db.session.scalar(sa.select(Loan.note).where(
            Loan.loan_code == "DEMO-LOAN-001")) == "Ghi chú do người dùng chỉnh sửa"
