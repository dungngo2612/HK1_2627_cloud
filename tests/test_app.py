from datetime import date

import pytest

from equipmentdesk import create_app
from equipmentdesk.config import PROJECT_ROOT, load_config
from equipmentdesk.models import Loan, LoanStatus, User


def test_login_page_and_static_without_database(app):
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    response = client.get("/login")
    assert response.status_code == 200
    assert "Đăng nhập" in response.get_data(as_text=True)
    assert client.get("/static/css/app.css").status_code == 200
    assert app.config["PORT"] == 8080
    assert app.config["APP_STORAGE_ROOT"] == PROJECT_ROOT / "data"
    assert {"sqlalchemy", "migrate", "csrf"} <= app.extensions.keys()
    assert app.login_manager is not None


@pytest.mark.parametrize("path", ["/", "/equipment", "/equipment/new", "/equipment/1", "/equipment/1/edit",
                                  "/loans", "/loans/new", "/loans/1"])
def test_anonymous_web_redirects_to_login(app, path):
    response = app.test_client().get(path)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/equipment"), ("GET", "/api/equipment/1/"),
    ("POST", "/api/equipment"), ("PUT", "/api/equipment/1"),
    ("GET", "/api/loans"), ("GET", "/api/loans/1/"),
    ("POST", "/api/loans"), ("POST", "/api/loans/1/return"),
])
def test_anonymous_api_returns_json_401_before_csrf(app, method, path):
    response = app.test_client().open(path, method=method)
    assert response.status_code == 401
    assert response.json["error"]["code"] == "authentication_required"
    assert "Location" not in response.headers


def test_login_requires_csrf_without_database(app):
    response = app.test_client().post("/login", data={"username": "demo", "password": "wrong"})
    assert response.status_code == 400
    assert "CSRF" in response.get_data(as_text=True)


def test_login_rejects_json_without_querying_database(app):
    client = app.test_client()
    token = client.get("/api/csrf-token").json["csrf_token"]
    response = client.post("/login", json={"username": {"bad": "type"}, "password": ["bad"]},
                           headers={"X-CSRFToken": token})
    assert response.status_code == 415
    assert "không nhận JSON" in response.get_data(as_text=True)


@pytest.mark.parametrize("path", ["/equipment", "/api/equipment"])
def test_database_failure_during_session_load_has_clear_error(app, monkeypatch, path):
    from sqlalchemy.exc import SQLAlchemyError
    from equipmentdesk.extensions import db

    def unavailable(*args, **kwargs):
        raise SQLAlchemyError("simulated connection failure")

    monkeypatch.setattr(db.session, "get", unavailable)
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = "1"
    response = client.get(path)
    assert response.status_code == 503
    if path.startswith("/api"):
        assert response.json["error"]["code"] == "database_unavailable"
    else:
        assert "Không thể truy cập database" in response.get_data(as_text=True)


@pytest.mark.parametrize("overrides, message", [
    ({"SECRET_KEY": None}, "SECRET_KEY"),
    ({"SECRET_KEY": "CHANGE_ME"}, "SECRET_KEY"),
    ({"SQLALCHEMY_DATABASE_URI": None}, "DATABASE_URL"),
    ({"SQLALCHEMY_DATABASE_URI": "sqlite:///local.db"}, "PostgreSQL"),
    ({"PORT": "invalid"}, "PORT"),
    ({"PORT": 65536}, "PORT"),
])
def test_invalid_config_fails_early(overrides, message):
    config = {"SECRET_KEY": "test-only-secret-key-never-use-in-a-real-app",
              "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://localhost/equipmentdesk_test"}
    config.update(overrides)
    with pytest.raises(ValueError, match=message):
        create_app(config)


def test_dotenv_does_not_override_environment(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("PORT=8888\nAPP_STORAGE_ROOT=./files\n")
    monkeypatch.setattr("equipmentdesk.config.PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.delenv("APP_STORAGE_ROOT", raising=False)
    config = load_config()
    assert config["PORT"] == "9090"
    assert config["APP_STORAGE_ROOT"] == "./files"


def test_password_hash_and_check():
    user = User(username="demo", full_name="Demo")
    user.set_password("local-test-password")
    assert user.password_hash != "local-test-password"
    assert user.check_password("local-test-password")
    assert not user.check_password("wrong-password")


@pytest.mark.parametrize("status, expected, today, overdue", [
    (LoanStatus.BORROWED, date(2026, 9, 24), date(2026, 9, 24), False),
    (LoanStatus.BORROWED, date(2026, 9, 24), date(2026, 9, 25), True),
    (LoanStatus.RETURNED, date(2026, 9, 24), date(2026, 9, 25), False),
])
def test_overdue_is_computed(status, expected, today, overdue):
    loan = Loan(status=status, expected_return_date=expected)
    assert loan.is_overdue_on(today) is overdue
