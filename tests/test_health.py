import pytest
from sqlalchemy.exc import SQLAlchemyError

from equipmentdesk.extensions import db
from equipmentdesk.storage.local import LocalStorage


def test_live_is_public_and_independent_of_dependencies(app, monkeypatch):
    def database_down(*args, **kwargs):
        raise SQLAlchemyError("secret database detail")

    def storage_down(*args, **kwargs):
        raise OSError("secret storage path")

    monkeypatch.setattr(db.session, "execute", database_down)
    monkeypatch.setattr(LocalStorage, "probe", storage_down)
    response = app.test_client().get("/health/live")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "database": "not_checked", "storage": "not_checked"}
    assert b"secret" not in response.data and b"traceback" not in response.data.lower()


def test_ready_reports_database_failure_without_leaking_details(app, monkeypatch, tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()

    def database_down(*args, **kwargs):
        raise SQLAlchemyError("not-a-real-secret and private host")

    monkeypatch.setattr(db.session, "execute", database_down)
    monkeypatch.setattr(LocalStorage, "probe", lambda self: None)
    app.config["APP_STORAGE_ROOT"] = tmp_path
    response = app.test_client().get("/health/ready")
    assert response.status_code == 503
    assert response.json == {"status": "not_ready", "database": "error", "storage": "ok"}
    assert b"not-a-real-secret" not in response.data and b"private host" not in response.data


def test_ready_reports_storage_failure_and_does_not_create_uploads(app, monkeypatch, tmp_path):
    class Result:
        @staticmethod
        def scalar_one():
            return 1

    monkeypatch.setattr(db.session, "execute", lambda *args, **kwargs: Result())
    app.config["APP_STORAGE_ROOT"] = tmp_path
    response = app.test_client().get("/health/ready")
    assert response.status_code == 503
    assert response.json == {"status": "not_ready", "database": "ok", "storage": "error"}
    assert not (tmp_path / "uploads").exists()


def test_ready_reports_write_failure_without_leaking_details(app, monkeypatch, tmp_path):
    class Result:
        @staticmethod
        def scalar_one():
            return 1

    def storage_down(self):
        raise OSError("private absolute path /private/example-only")

    monkeypatch.setattr(db.session, "execute", lambda *args, **kwargs: Result())
    monkeypatch.setattr(LocalStorage, "probe", storage_down)
    (tmp_path / "uploads").mkdir(parents=True)
    app.config["APP_STORAGE_ROOT"] = tmp_path
    response = app.test_client().get("/health/ready")
    assert response.status_code == 503
    assert response.json == {"status": "not_ready", "database": "ok", "storage": "error"}
    assert b"/private/example-only" not in response.data and b"traceback" not in response.data.lower()


@pytest.mark.postgresql
def test_ready_returns_200_with_database_and_writable_storage(postgres_app, tmp_path):
    postgres_app.config["APP_STORAGE_ROOT"] = tmp_path
    (tmp_path / "uploads").mkdir()
    response = postgres_app.test_client().get("/health/ready")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "database": "ok", "storage": "ok"}
    assert list((tmp_path / "uploads").iterdir()) == []
