from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from equipmentdesk.extensions import db
from equipmentdesk.models import Attachment, Equipment, Loan, User
from equipmentdesk.storage.local import LocalStorage, UnsafeStoragePath

pytestmark = pytest.mark.postgresql
PASSWORD = "attachment-test-password"


def pdf_bytes():
    target = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(target)
    return target.getvalue()


def image_bytes(format):
    target = BytesIO()
    Image.new("RGB", (4, 3), (12, 34, 56)).save(target, format=format)
    return target.getvalue()


@pytest.fixture
def attachment_env(postgres_app, tmp_path):
    previous = postgres_app.config["APP_STORAGE_ROOT"]
    postgres_app.config["APP_STORAGE_ROOT"] = tmp_path / "attachment-root"
    try:
        with postgres_app.app_context():
            user = User(username="file-user-" + uuid4().hex, full_name="Người lưu biên bản")
            user.set_password(PASSWORD)
            device = Equipment(code="FILE-EQ-" + uuid4().hex, name="Laptop", category="Demo")
            db.session.add_all([user, device])
            db.session.flush()
            loan = Loan(loan_code="FILE-LOAN-" + uuid4().hex, user_id=user.id,
                        loan_date=date.today(), expected_return_date=date.today())
            db.session.add(loan)
            db.session.commit()
            loan_id, username = loan.id, user.username
        yield postgres_app, loan_id, username, tmp_path
    finally:
        postgres_app.config["APP_STORAGE_ROOT"] = previous


@pytest.fixture
def attachment_client(attachment_env):
    app, _, username, _ = attachment_env
    client = app.test_client()
    token = client.get("/api/csrf-token").json["csrf_token"]
    response = client.post("/login", data={"csrf_token": token, "username": username, "password": PASSWORD})
    assert response.status_code == 303
    return client


def csrf(client):
    return client.get("/api/csrf-token").json["csrf_token"]


def upload(client, loan_id, data, filename="bien-ban.pdf", *, declared="application/octet-stream", path=None, include_token=True):
    path = path or f"/api/loans/{loan_id}/attachments"
    return client.post(path, data={"file": (BytesIO(data), filename, declared),
                                   **({"csrf_token": csrf(client)} if include_token and not path.startswith("/api/") else {})},
                       headers={"X-CSRFToken": csrf(client)} if include_token and path.startswith("/api/") else {},
                       content_type="multipart/form-data")


def rows(app, loan_id):
    with app.app_context():
        return db.session.scalars(sa.select(Attachment).where(Attachment.loan_id == loan_id)).all()


def files(app):
    root = app.config["APP_STORAGE_ROOT"] / "uploads"
    return list(root.iterdir()) if root.exists() and root.is_dir() else []


@pytest.mark.parametrize("data,mime,ext,original", [
    (pdf_bytes(), "application/pdf", ".pdf", "bien-ban.pdf"),
    (image_bytes("PNG"), "image/png", ".png", "anh.png"),
    (image_bytes("JPEG"), "image/jpeg", ".jpg", "anh.jpeg"),
])
def test_upload_download_exact_bytes_metadata_and_web_list(attachment_env, attachment_client, data, mime, ext, original):
    app, loan_id, _, _ = attachment_env
    # Client declaration is deliberately wrong; the parser must detect the actual bytes.
    response = upload(attachment_client, loan_id, data, original, declared="text/plain")
    assert response.status_code == 201
    metadata = response.json
    assert metadata["loan_id"] == loan_id and metadata["content_type"] == mime
    assert metadata["original_name"] == original and metadata["size"] == len(data)
    assert metadata["sha256"] == sha256(data).hexdigest()
    assert UUID(metadata["id"]).version == 4
    assert metadata["relative_path"] == f"uploads/{UUID(metadata['id']).hex}{ext}"
    assert not Path(metadata["relative_path"]).is_absolute()
    assert (app.config["APP_STORAGE_ROOT"] / metadata["relative_path"]).read_bytes() == data
    assert response.headers["Location"] == f"/api/attachments/{metadata['id']}"
    assert attachment_client.get(response.headers["Location"] + "/").json == metadata
    downloaded = attachment_client.get(response.headers["Location"] + "/download")
    assert downloaded.status_code == 200 and downloaded.data == data
    assert downloaded.mimetype == mime
    assert downloaded.headers["Content-Disposition"].startswith("attachment;")
    assert downloaded.headers["X-Content-Type-Options"] == "nosniff"
    assert original.rsplit(".", 1)[0] in downloaded.headers["Content-Disposition"]
    page = attachment_client.get(f"/loans/{loan_id}").get_data(as_text=True)
    assert original in page and f"/api/attachments/{metadata['id']}/download" in page
    assert len(rows(app, loan_id)) == 1 and len(files(app)) == 1


def test_web_upload_form_and_download(attachment_env, attachment_client):
    app, loan_id, _, _ = attachment_env
    page = attachment_client.get(f"/loans/{loan_id}").get_data(as_text=True)
    assert 'enctype="multipart/form-data"' in page and "Biên bản đính kèm" in page
    data = pdf_bytes()
    response = upload(attachment_client, loan_id, data, "web.pdf", path=f"/loans/{loan_id}/attachments")
    assert response.status_code == 303 and response.headers["Location"] == f"/loans/{loan_id}"
    stored = rows(app, loan_id)[0]
    assert attachment_client.get(f"/api/attachments/{stored.id}/download").data == data
    page = attachment_client.get(f"/loans/{loan_id}").get_data(as_text=True)
    assert "web.pdf" in page and "Tải xuống" in page


@pytest.mark.parametrize("bad", [b"", b"plain text", b"<html>fake</html>", b"%PDF-1.4\n%%EOF", b"\x89PNG\r\n\x1a\nnot a png", b"\xff\xd8\xffnot a jpeg"])
def test_reject_empty_wrong_or_forged_type(attachment_env, attachment_client, bad):
    app, loan_id, _, _ = attachment_env
    response = upload(attachment_client, loan_id, bad, "fake.pdf", declared="application/pdf")
    assert response.status_code == 422 and response.json["error"]["fields"].get("file")
    assert not rows(app, loan_id) and not files(app)


def test_reject_file_over_ten_mibibytes(attachment_env, attachment_client):
    app, loan_id, _, _ = attachment_env
    response = upload(attachment_client, loan_id, b"x" * (10 * 1024 * 1024 + 1), "huge.pdf")
    assert response.status_code == 413
    assert not rows(app, loan_id) and not files(app)


def test_missing_physical_file_reports_404(attachment_env, attachment_client):
    app, loan_id, _, _ = attachment_env
    metadata = upload(attachment_client, loan_id, pdf_bytes()).json
    (app.config["APP_STORAGE_ROOT"] / metadata["relative_path"]).unlink()
    assert attachment_client.get(f"/api/attachments/{metadata['id']}").status_code == 200
    download = attachment_client.get(f"/api/attachments/{metadata['id']}/download")
    assert download.status_code == 404 and download.json["error"]["code"] == "file_missing"
    assert len(rows(app, loan_id)) == 1
    assert "bien-ban.pdf" in attachment_client.get(f"/loans/{loan_id}").get_data(as_text=True)


def test_db_failure_after_file_written_removes_it(attachment_env, attachment_client):
    app, loan_id, _, _ = attachment_env
    attempts = []

    def fail_after_flush(session, context):
        if any(isinstance(obj, Attachment) for obj in session.new):
            attempts.append(True)
            raise SQLAlchemyError("injected attachment database error after INSERT")

    sa.event.listen(Session, "after_flush", fail_after_flush)
    try:
        response = upload(attachment_client, loan_id, pdf_bytes())
    finally:
        sa.event.remove(Session, "after_flush", fail_after_flush)
    assert attempts and response.status_code == 503
    assert response.json["error"]["code"] == "database_unavailable"
    assert not rows(app, loan_id) and not files(app)


def test_db_rejects_file_without_loan_and_does_not_save(attachment_env, attachment_client):
    app, loan_id, _, _ = attachment_env
    result = upload(attachment_client, 9223372036854775807, pdf_bytes())
    assert result.status_code == 404 and not files(app)
    assert not rows(app, loan_id)


def test_path_traversal_and_symlink_rejected(attachment_env, attachment_client):
    app, loan_id, _, outside = attachment_env
    metadata = upload(attachment_client, loan_id, pdf_bytes(), "../internal.pdf").json
    assert metadata["original_name"] == "internal.pdf"
    identifier = UUID(metadata["id"])
    storage = LocalStorage(app.config["APP_STORAGE_ROOT"])
    for value in ("../../secret.pdf", "/etc/passwd", f"uploads/{uuid4().hex}.pdf", f"uploads/{identifier.hex}/../x.pdf"):
        with pytest.raises(UnsafeStoragePath):
            storage.read(value, identifier, 10 * 1024 * 1024)
    upload_path = app.config["APP_STORAGE_ROOT"] / "uploads"
    (upload_path / (identifier.hex + ".pdf")).unlink()
    upload_path.rmdir()
    target = outside / "outside"
    target.mkdir()
    upload_path.symlink_to(target, target_is_directory=True)
    result = upload(attachment_client, loan_id, pdf_bytes(), "symlink.pdf")
    assert result.status_code == 503 and list(target.iterdir()) == []
    assert len(rows(app, loan_id)) == 1


def test_tampered_metadata_path_and_file_integrity(attachment_env, attachment_client):
    app, loan_id, _, _ = attachment_env
    payload = pdf_bytes()
    metadata = upload(attachment_client, loan_id, payload).json
    path = app.config["APP_STORAGE_ROOT"] / metadata["relative_path"]
    path.write_bytes(payload + b"changed")
    url = f"/api/attachments/{metadata['id']}/download"
    result = attachment_client.get(url)
    assert result.status_code == 409 and result.json["error"]["code"] == "file_integrity_error"
    with app.app_context():
        row = db.session.get(Attachment, UUID(metadata["id"]))
        row.relative_path = f"uploads/{uuid4().hex}.pdf"
        db.session.commit()
    result = attachment_client.get(url)
    assert result.status_code == 409 and result.json["error"]["code"] == "unsafe_storage_path"


def test_original_name_is_safely_processed_for_download(attachment_env, attachment_client):
    app, loan_id, _, _ = attachment_env
    data = image_bytes("PNG")
    result = upload(attachment_client, loan_id, data, "..\\folder\\biên bản.pdf", declared="application/pdf")
    assert result.status_code == 201, result.get_data(as_text=True)
    metadata = result.json
    assert metadata["original_name"] == "biên bản.pdf"
    assert metadata["content_type"] == "image/png"
    response = attachment_client.get(f"/api/attachments/{metadata['id']}/download")
    assert response.status_code == 200 and response.data == data
    disposition = response.headers["Content-Disposition"]
    assert "attachment;" in disposition and ".." not in disposition and "\\r" not in disposition and "\\n" not in disposition
    assert disposition.endswith('filename=bien_ban.png')


def test_authentication_and_csrf(attachment_env, attachment_client):
    app, loan_id, _, _ = attachment_env
    guest = app.test_client()
    assert guest.get(f"/api/attachments/{uuid4()}").status_code == 401
    assert guest.get(f"/api/attachments/{uuid4()}/download").status_code == 401
    assert upload(guest, loan_id, pdf_bytes(), include_token=False).status_code == 401
    assert guest.get(f"/loans/{loan_id}").status_code == 302
    assert attachment_client.post(f"/loans/{loan_id}/attachments", data={"file": (BytesIO(pdf_bytes()), "x.pdf")},
                                  content_type="multipart/form-data").status_code == 400
    assert not rows(app, loan_id) and not files(app)
