import json
from uuid import uuid4

import pytest
import sqlalchemy as sa

from equipmentdesk.extensions import db
from equipmentdesk.models import Equipment, User

pytestmark = pytest.mark.postgresql
PASSWORD = "test-demo-password-123"


def token(client):
    response = client.get("/api/csrf-token")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    return response.json["csrf_token"]


def credentials():
    return {"code": "EQ-" + uuid4().hex, "name": "Máy tính xách tay", "category": "Máy tính",
            "description": "Thiết bị dùng chung", "location": "Phòng 201", "status": "AVAILABLE"}


@pytest.fixture
def visitor(postgres_app):
    username = "user-" + uuid4().hex
    with postgres_app.app_context():
        user = User(username=username, full_name="Người vận hành demo")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
    return postgres_app.test_client(), username


@pytest.fixture
def logged_in(visitor):
    client, username = visitor
    response = client.post("/login", data={"username": username, "password": PASSWORD, "csrf_token": token(client)})
    assert response.status_code == 303
    return client


def post_equipment(client, payload):
    return client.post("/api/equipment", json=payload, headers={"X-CSRFToken": token(client)})


def put_equipment(client, equipment_id, payload):
    return client.put(f"/api/equipment/{equipment_id}", json=payload, headers={"X-CSRFToken": token(client)})


def test_correct_login_session_rotation_and_logout(visitor):
    client, username = visitor
    before = token(client)
    response = client.post("/login?next=https://example.com", data={
        "username": username, "password": PASSWORD, "csrf_token": before})
    assert response.status_code == 303
    assert response.headers["Location"] == "/equipment"
    with client.session_transaction() as session:
        assert "_user_id" in session
        assert PASSWORD not in str(dict(session))
    assert token(client) != before
    assert client.get("/equipment").status_code == 200
    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 400
    assert client.get("/api/equipment").status_code == 200
    assert client.post("/logout", data={"csrf_token": token(client)}).status_code == 303
    assert client.get("/api/equipment").status_code == 401
    assert client.get("/equipment").status_code == 302


@pytest.mark.parametrize("unknown", [False, True])
def test_wrong_login_has_generic_error_and_no_session(visitor, unknown):
    client, username = visitor
    response = client.post("/login", data={"username": "missing-" + username if unknown else username,
                                            "password": "wrong-password", "csrf_token": token(client)})
    assert response.status_code == 401
    assert "Tên đăng nhập hoặc mật khẩu không đúng." in response.get_data(as_text=True)
    with client.session_transaction() as session:
        assert "_user_id" not in session
    assert client.get("/api/equipment").status_code == 401


def test_login_rejects_token_from_another_session(visitor, postgres_app):
    client, username = visitor
    token(client)
    other_token = token(postgres_app.test_client())
    response = client.post("/login", data={"username": username, "password": PASSWORD, "csrf_token": other_token})
    assert response.status_code == 400
    assert client.get("/api/equipment").status_code == 401


def test_api_create_search_detail_update_and_slashes(logged_in):
    payload = credentials()
    created = post_equipment(logged_in, payload)
    assert created.status_code == 201
    item = created.json
    assert {key: item[key] for key in payload} == payload
    assert item["created_at"] and item["updated_at"]
    assert created.headers["Location"] == f"/api/equipment/{item['id']}"
    assert logged_in.get(created.headers["Location"] + "/").json == item
    found = logged_in.get("/api/equipment/", query_string={"q": payload["code"].lower()})
    assert found.json["total"] == 1
    assert found.json["items"][0]["id"] == item["id"]
    payload.update(name="Máy tính đã cập nhật", status="MAINTENANCE")
    updated = put_equipment(logged_in, item["id"], payload)
    assert updated.status_code == 200
    assert updated.json["name"] == payload["name"]
    assert updated.json["status"] == "MAINTENANCE"
    assert logged_in.get(f"/equipment/{item['id']}").status_code == 200
    assert logged_in.get(f"/equipment/{item['id']}/edit").status_code == 200


def test_web_create_edit_search_and_escape(logged_in):
    assert logged_in.get("/equipment/new").status_code == 200
    payload = credentials()
    payload["name"] = '<script>alert("xss")</script>'
    created = logged_in.post("/equipment/new", data={**payload, "csrf_token": token(logged_in)})
    assert created.status_code == 303
    detail_url = created.headers["Location"]
    page = logged_in.get(detail_url).get_data(as_text=True)
    assert "&lt;script&gt;" in page
    assert '<script>alert("xss")</script>' not in page
    payload.update(name="Máy chiếu", status="MAINTENANCE", location="Phòng hội nghị")
    updated = logged_in.post(detail_url + "/edit", data={**payload, "csrf_token": token(logged_in)})
    assert updated.status_code == 303
    page = logged_in.get(detail_url).get_data(as_text=True)
    assert "Máy chiếu" in page and "Bảo trì" in page
    listing = logged_in.get("/equipment", query_string={"q": payload["code"]}).get_data(as_text=True)
    assert "1 thiết bị" in listing and "Máy chiếu" in listing


@pytest.mark.parametrize("path", ["/api/equipment", "/equipment/new"])
def test_creation_without_csrf_is_rejected(logged_in, path):
    payload = credentials()
    response = logged_in.post(path, json=payload) if path.startswith("/api") else logged_in.post(path, data=payload)
    assert response.status_code == 400
    if path.startswith("/api"):
        assert response.json["error"]["code"] == "csrf_error"
    assert logged_in.get("/api/equipment", query_string={"q": payload["code"]}).json["total"] == 0


def test_update_requires_csrf_and_tokens_expire(logged_in, postgres_app, monkeypatch):
    payload = credentials()
    item = post_equipment(logged_in, payload).json
    url = f"/api/equipment/{item['id']}"
    payload["name"] = "Không được lưu"
    assert logged_in.put(url, json=payload).status_code == 400
    assert logged_in.post(f"/equipment/{item['id']}/edit", data=payload).status_code == 400
    old_token = token(logged_in)
    monkeypatch.setitem(postgres_app.config, "WTF_CSRF_TIME_LIMIT", -1)
    response = logged_in.put(url, json=payload, headers={"X-CSRFToken": old_token})
    assert response.status_code == 400 and response.json["error"]["code"] == "csrf_error"
    assert logged_in.get(url).json["name"] == item["name"]


@pytest.mark.parametrize("field,value", [
    ("code", "   "), ("name", ""), ("category", None), ("name", ["invalid"]),
    ("code", "x" * 81), ("name", "x" * 201), ("category", "x" * 101),
    ("location", "x" * 201), ("description", "x" * 10001),
    ("description", 10), ("name", "bad\x00value"),
    ("status", "INVALID"), ("status", "BORROWED"), ("status", {}), ("id", 10),
])
def test_api_validation_rejects_invalid_values(logged_in, field, value):
    payload = credentials()
    payload[field] = value
    response = post_equipment(logged_in, payload)
    assert response.status_code == 422
    assert response.json["error"]["fields"].get(field if field != "id" else "_form")


@pytest.mark.parametrize("payload", [[], "text", None, {}])
def test_api_requires_object_and_required_fields(logged_in, payload):
    response = logged_in.post("/api/equipment", data=json.dumps(payload),
                              content_type="application/json", headers={"X-CSRFToken": token(logged_in)})
    assert response.status_code == 422
    assert response.is_json


def test_api_malformed_json_and_content_type(logged_in):
    headers = {"X-CSRFToken": token(logged_in)}
    assert logged_in.post("/api/equipment", data="{broken", content_type="application/json", headers=headers).status_code == 400
    response = logged_in.post("/api/equipment", data="name=value", headers=headers)
    assert response.status_code == 415 and response.is_json


def test_web_and_api_share_validation_and_duplicate_error(logged_in):
    payload = credentials()
    created = post_equipment(logged_in, payload)
    duplicate = logged_in.post("/equipment/new", data={**payload, "csrf_token": token(logged_in)})
    assert duplicate.status_code == 409
    assert "Mã thiết bị đã tồn tại" in duplicate.get_data(as_text=True)
    assert post_equipment(logged_in, payload).json["error"]["code"] == "duplicate_code"
    payload["code"] = " "
    web = logged_in.post("/equipment/new", data={**payload, "csrf_token": token(logged_in)})
    api = post_equipment(logged_in, payload)
    assert web.status_code == api.status_code == 422
    assert api.json["error"]["fields"]["code"][0] in web.get_data(as_text=True)
    assert logged_in.get(created.headers["Location"]).status_code == 200


def test_duplicate_edit_rolls_back_all_changes(logged_in):
    first = post_equipment(logged_in, credentials()).json
    payload = credentials()
    second = post_equipment(logged_in, payload).json
    payload.update(code=first["code"], name="Must not be saved")
    response = put_equipment(logged_in, second["id"], payload)
    assert response.status_code == 409
    unchanged = logged_in.get(f"/api/equipment/{second['id']}").json
    assert unchanged["code"] == second["code"] and unchanged["name"] == second["name"]


@pytest.mark.parametrize("new_status", ["AVAILABLE", "MAINTENANCE"])
def test_cannot_leave_borrowed_through_web_or_api(logged_in, postgres_app, new_status):
    payload = credentials()
    item = post_equipment(logged_in, payload).json
    with postgres_app.app_context():
        db.session.get(Equipment, item["id"]).status = "BORROWED"
        db.session.commit()
    payload.update(status=new_status, name="Must not be saved")
    api = put_equipment(logged_in, item["id"], payload)
    assert api.status_code == 409 and api.json["error"]["code"] == "borrowed_equipment"
    web = logged_in.post(f"/equipment/{item['id']}/edit", data={**payload, "csrf_token": token(logged_in)})
    assert web.status_code == 409
    unchanged = logged_in.get(f"/api/equipment/{item['id']}").json
    assert unchanged["status"] == "BORROWED" and unchanged["name"] == item["name"]
    # Metadata editing is allowed when the BORROWED status is unchanged/omitted.
    payload.pop("status")
    payload["name"] = "Thông tin được sửa"
    assert put_equipment(logged_in, item["id"], payload).json["status"] == "BORROWED"
    web = logged_in.post(f"/equipment/{item['id']}/edit", data={**payload, "csrf_token": token(logged_in)})
    assert web.status_code == 303


def test_cannot_enter_borrowed_through_edit(logged_in):
    payload = credentials()
    item = post_equipment(logged_in, payload).json
    payload["status"] = "BORROWED"
    assert put_equipment(logged_in, item["id"], payload).status_code == 422
    assert logged_in.post(f"/equipment/{item['id']}/edit", data={**payload, "csrf_token": token(logged_in)}).status_code == 422
    assert logged_in.get(f"/api/equipment/{item['id']}").json["status"] == "AVAILABLE"


def test_missing_resources_and_bad_search(logged_in):
    for identifier in (0, 9999999, 9223372036854775808):
        assert logged_in.get(f"/api/equipment/{identifier}").status_code == 404
        assert put_equipment(logged_in, identifier, credentials()).status_code == 404
        assert logged_in.get(f"/equipment/{identifier}").status_code == 404
    for page in ("abc", "0", "-1"):
        response = logged_in.get("/api/equipment", query_string={"page": page})
        assert response.status_code == 400 and response.is_json
    assert logged_in.get("/api/equipment", query_string={"q": "x" * 201}).status_code == 422
    assert logged_in.get("/api/equipment", query_string={"q": "bad\x00query"}).status_code == 422


def test_search_pagination_and_literal_wildcards(logged_in, postgres_app):
    prefix = "SEARCH-" + uuid4().hex
    with postgres_app.app_context():
        db.session.add_all([Equipment(code=f"{prefix}-{i}", name="Máy chiếu", category="Demo") for i in range(21)])
        db.session.add(Equipment(code=prefix + "-percent", name="100% test", category="Demo"))
        db.session.commit()
    first = logged_in.get("/api/equipment", query_string={"q": prefix}).json
    second = logged_in.get("/api/equipment", query_string={"q": prefix, "page": 2}).json
    assert first["total"] == 22 and len(first["items"]) == 20 and len(second["items"]) == 2
    assert not {item["id"] for item in first["items"]} & {item["id"] for item in second["items"]}
    literal = logged_in.get("/api/equipment", query_string={"q": "%"}).json
    assert literal["total"] == 1
    assert literal["items"][0]["name"] == "100% test"
    assert "Trang sau" in logged_in.get("/equipment", query_string={"q": prefix}).get_data(as_text=True)


def test_cli_create_is_idempotent_and_preserves_password(postgres_app, monkeypatch):
    username = "cli-" + uuid4().hex
    monkeypatch.setenv("DEMO_USERNAME", username)
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    runner = postgres_app.test_cli_runner()
    first = runner.invoke(args=["create-demo-user"])
    assert first.exit_code == 0 and "Đã tạo" in first.output
    with postgres_app.app_context():
        user = db.session.scalar(sa.select(User).where(User.username == username))
        original_hash = user.password_hash
        assert user.check_password(PASSWORD) and original_hash != PASSWORD
    monkeypatch.setenv("DEMO_PASSWORD", "different-password-456")
    second = runner.invoke(args=["create-demo-user"])
    assert second.exit_code == 0 and "đã tồn tại" in second.output
    with postgres_app.app_context():
        users = db.session.scalars(sa.select(User).where(User.username == username)).all()
        assert len(users) == 1 and users[0].password_hash == original_hash
        assert not users[0].check_password("different-password-456")
    assert PASSWORD not in first.output + second.output


@pytest.mark.parametrize("username,password", [(None, None), ("", PASSWORD), ("x" * 81, PASSWORD), ("new-user", "short")])
def test_cli_rejects_missing_or_invalid_environment(postgres_app, monkeypatch, username, password):
    for key, value in (("DEMO_USERNAME", username), ("DEMO_PASSWORD", password)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    result = postgres_app.test_cli_runner().invoke(args=["create-demo-user"])
    assert result.exit_code != 0 and "Error:" in result.output
