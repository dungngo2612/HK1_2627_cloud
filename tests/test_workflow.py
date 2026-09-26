from datetime import date, timedelta
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

import pytest
import sqlalchemy as sa
from pypdf import PdfWriter

from equipmentdesk.extensions import db
from equipmentdesk.models import Attachment, Equipment, Loan, User

pytestmark = pytest.mark.postgresql
PASSWORD = "workflow-test-password-123"


def csrf(client):
    response = client.get("/api/csrf-token")
    assert response.status_code == 200
    return response.json["csrf_token"]


def valid_pdf():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=320, height=240)
    writer.write(output)
    return output.getvalue()


def test_complete_web_flow_login_borrow_upload_download_return(postgres_app, tmp_path):
    root = tmp_path / "workflow-storage"
    old_root = postgres_app.config["APP_STORAGE_ROOT"]
    postgres_app.config["APP_STORAGE_ROOT"] = root
    try:
        with postgres_app.app_context():
            user = User(username="workflow-" + uuid4().hex, full_name="Người dùng luồng mẫu")
            user.set_password(PASSWORD)
            equipment = Equipment(code="FLOW-EQ-" + uuid4().hex,
                                  name="Máy chiếu thử luồng", category="Trình chiếu",
                                  location="Phòng 201")
            db.session.add_all([user, equipment])
            db.session.commit()
            username, equipment_id, equipment_code = user.username, equipment.id, equipment.code

        client = postgres_app.test_client()
        assert client.get("/").status_code == 302
        login_page = client.get("/login")
        assert login_page.status_code == 200 and 'name="csrf_token"' in login_page.get_data(as_text=True)
        login = client.post("/login", data={"username": username, "password": PASSWORD,
                                            "csrf_token": csrf(client)})
        assert login.status_code == 303 and login.headers["Location"] == "/equipment"

        listing = client.get("/equipment")
        assert listing.status_code == 200 and equipment_code in listing.get_data(as_text=True)
        assert client.get(f"/equipment/{equipment_id}").status_code == 200
        new_loan_page = client.get("/loans/new").get_data(as_text=True)
        assert equipment_code in new_loan_page and "condition_before_" in new_loan_page

        today = date.today()
        created = client.post("/loans/new", data={
            "csrf_token": csrf(client),
            "loan_date": today.isoformat(),
            "expected_return_date": (today + timedelta(days=7)).isoformat(),
            "note": "Kiểm tra luồng đầy đủ",
            "equipment_ids": str(equipment_id),
            f"condition_before_{equipment_id}": "Hoạt động tốt trước khi mượn",
        })
        assert created.status_code == 303
        detail_url = created.headers["Location"]
        detail = client.get(detail_url)
        assert detail.status_code == 200
        assert "Đang mượn" in detail.get_data(as_text=True)
        loan_id = int(detail_url.rsplit("/", 1)[-1])

        pdf = valid_pdf()
        uploaded = client.post(f"{detail_url}/attachments", data={
            "csrf_token": csrf(client),
            "file": (BytesIO(pdf), "bien-ban-flow.pdf", "application/pdf"),
        }, content_type="multipart/form-data")
        assert uploaded.status_code == 303 and uploaded.headers["Location"] == detail_url
        detail = client.get(detail_url).get_data(as_text=True)
        assert "bien-ban-flow.pdf" in detail and "/api/attachments/" in detail

        with postgres_app.app_context():
            loan = db.session.get(Loan, loan_id)
            attachment = db.session.scalar(sa.select(Attachment).where(Attachment.loan_id == loan_id))
            assert loan.status == "BORROWED" and loan.items[0].equipment.status == "BORROWED"
            attachment_id = attachment.id
            assert attachment.sha256 == sha256(pdf).hexdigest()
        downloaded = client.get(f"/api/attachments/{attachment_id}/download")
        assert downloaded.status_code == 200
        assert downloaded.data == pdf
        assert downloaded.headers["Content-Disposition"].startswith("attachment;")

        returned = client.post(f"{detail_url}/return", data={
            "csrf_token": csrf(client),
            "actual_return_date": today.isoformat(),
            "equipment_ids": str(equipment_id),
            f"condition_after_{equipment_id}": "Đã kiểm tra, đủ phụ kiện",
        })
        assert returned.status_code == 303 and returned.headers["Location"] == detail_url
        completed_page = client.get(detail_url).get_data(as_text=True)
        assert "Đã trả" in completed_page
        assert "Xác nhận trả toàn bộ phiếu" not in completed_page
        equipment_page = client.get(f"/equipment/{equipment_id}").get_data(as_text=True)
        assert "Sẵn sàng" in equipment_page

        with postgres_app.app_context():
            loan = db.session.get(Loan, loan_id)
            equipment = db.session.get(Equipment, equipment_id)
            assert loan.status == "RETURNED" and loan.actual_return_date == today
            assert loan.items[0].condition_after == "Đã kiểm tra, đủ phụ kiện"
            assert equipment.status == "AVAILABLE"
    finally:
        postgres_app.config["APP_STORAGE_ROOT"] = old_root
