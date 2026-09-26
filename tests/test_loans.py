from datetime import date, timedelta
import json
from threading import Event, Thread, current_thread
from time import monotonic, sleep
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from werkzeug.datastructures import MultiDict

from equipmentdesk.extensions import db
from equipmentdesk.models import Equipment, Loan, LoanItem, User
from equipmentdesk.services import loans as service

pytestmark = pytest.mark.postgresql
PASSWORD = "loan-test-password-123"


def csrf(client):
    return client.get("/api/csrf-token").json["csrf_token"]


def login_client(app, username):
    client = app.test_client()
    result = client.post("/login", data={"username": username, "password": PASSWORD, "csrf_token": csrf(client)})
    assert result.status_code == 303
    return client


@pytest.fixture
def loan_data(postgres_app):
    with postgres_app.app_context():
        user = User(username="loan-user-" + uuid4().hex, full_name="Người tạo phiếu")
        user.set_password(PASSWORD)
        equipment = [Equipment(code="LOAN-EQ-" + uuid4().hex, name=f"Thiết bị {i}", category="Demo") for i in range(3)]
        db.session.add_all([user, *equipment])
        db.session.commit()
        return {"user_id": user.id, "username": user.username, "ids": [row.id for row in equipment]}


@pytest.fixture
def loan_client(postgres_app, loan_data):
    return login_client(postgres_app, loan_data["username"])


def borrow_payload(ids):
    return {"loan_date": date.today().isoformat(), "expected_return_date": (date.today() + timedelta(days=7)).isoformat(),
            "note": "Mượn phục vụ buổi học", "items": [{"equipment_id": i, "condition_before": "Hoạt động tốt"} for i in ids]}


def return_payload(ids):
    return {"actual_return_date": date.today().isoformat(),
            "items": [{"equipment_id": i, "condition_after": "Đầy đủ phụ kiện"} for i in ids]}


def borrow(client, payload):
    return client.post("/api/loans", json=payload, headers={"X-CSRFToken": csrf(client)})


def give_back(client, loan_id, payload):
    return client.post(f"/api/loans/{loan_id}/return", json=payload, headers={"X-CSRFToken": csrf(client)})


def snapshot(app, data):
    with app.app_context():
        loans = db.session.scalars(sa.select(Loan).where(Loan.user_id == data["user_id"]).order_by(Loan.id)).all()
        equipment = db.session.scalars(sa.select(Equipment).where(Equipment.id.in_(data["ids"])).order_by(Equipment.id)).all()
        return {
            "loans": [(row.id, row.status, row.actual_return_date,
                       [(item.equipment_id, item.condition_before, item.condition_after) for item in sorted(row.items, key=lambda x: x.id)])
                      for row in loans],
            "equipment": [(row.id, row.status) for row in equipment],
        }


def test_create_many_detail_list_and_session_owner(loan_client, loan_data, postgres_app):
    ids = loan_data["ids"][:2][::-1]
    response = borrow(loan_client, borrow_payload(ids))
    assert response.status_code == 201
    loan = response.json
    assert response.headers["Location"] == f"/api/loans/{loan['id']}"
    assert loan["loan_code"].startswith("PM-") and loan["user_id"] == loan_data["user_id"]
    assert loan["status"] == "BORROWED" and loan["actual_return_date"] is None
    assert loan["item_count"] == 2 and [item["equipment_id"] for item in loan["items"]] == sorted(ids)
    assert all(item["condition_before"] == "Hoạt động tốt" and item["condition_after"] is None for item in loan["items"])
    assert loan_client.get(response.headers["Location"] + "/").json == loan
    listing = loan_client.get("/api/loans/").json
    assert listing["items"][0]["id"] == loan["id"] and listing["per_page"] == 20
    states = dict(snapshot(postgres_app, loan_data)["equipment"])
    assert all(states[i] == "BORROWED" for i in ids)
    assert states[loan_data["ids"][2]] == "AVAILABLE"


def test_return_all_then_reborrow_and_reject_second_return(loan_client, loan_data, postgres_app):
    ids = loan_data["ids"][:2]
    loan = borrow(loan_client, borrow_payload(ids)).json
    result = give_back(loan_client, loan["id"], return_payload(ids))
    assert result.status_code == 200
    assert result.json["status"] == "RETURNED" and result.json["actual_return_date"] == date.today().isoformat()
    assert all(item["condition_after"] == "Đầy đủ phụ kiện" for item in result.json["items"])
    assert all(status == "AVAILABLE" for _, status in snapshot(postgres_app, loan_data)["equipment"])
    second = borrow(loan_client, borrow_payload(ids))
    assert second.status_code == 201
    before = snapshot(postgres_app, loan_data)
    repeated = give_back(loan_client, loan["id"], return_payload(ids))
    assert repeated.status_code == 409 and repeated.json["error"]["code"] == "already_returned"
    assert snapshot(postgres_app, loan_data) == before


@pytest.mark.parametrize("invalid", ["empty", "duplicate", "missing", "string_id", "boolean_id", "bad_condition",
                                      "date_order", "bad_date", "compact_date", "user_id", "loan_code", "status",
                                      "extra_item_field", "many", "note_type", "items_type"])
def test_invalid_borrow_rolls_back(loan_client, loan_data, postgres_app, invalid):
    ids = loan_data["ids"][:2]
    payload = borrow_payload(ids)
    if invalid == "empty": payload["items"] = []
    elif invalid == "duplicate": payload["items"].append(payload["items"][0].copy())
    elif invalid == "missing": payload.pop("items")
    elif invalid == "string_id": payload["items"][0]["equipment_id"] = str(ids[0])
    elif invalid == "boolean_id": payload["items"][0]["equipment_id"] = True
    elif invalid == "bad_condition": payload["items"][1]["condition_before"] = " "
    elif invalid == "date_order": payload["expected_return_date"] = (date.today() - timedelta(days=1)).isoformat()
    elif invalid == "bad_date": payload["loan_date"] = "2026-02-30"
    elif invalid == "compact_date": payload["loan_date"] = "20260924"
    elif invalid == "extra_item_field": payload["items"][0]["quantity"] = 2
    elif invalid == "many": payload["items"] *= 51
    elif invalid == "note_type": payload["note"] = ["not text"]
    elif invalid == "items_type": payload["items"] = "not a list"
    else: payload[invalid] = 999 if invalid == "user_id" else "client_value"
    before = snapshot(postgres_app, loan_data)
    response = borrow(loan_client, payload)
    assert response.status_code == 422 and response.json["error"]["fields"]
    assert snapshot(postgres_app, loan_data) == before


@pytest.mark.parametrize("invalid", ["MAINTENANCE", "BORROWED", "missing"])
def test_one_unavailable_device_rejects_whole_loan(loan_client, loan_data, postgres_app, invalid):
    ids = loan_data["ids"][:2]
    if invalid == "missing":
        ids[1] = 9223372036854775807
    elif invalid == "BORROWED":
        assert borrow(loan_client, borrow_payload([ids[1]])).status_code == 201
    else:
        with postgres_app.app_context():
            db.session.get(Equipment, ids[1]).status = invalid
            db.session.commit()
    before = snapshot(postgres_app, loan_data)
    response = borrow(loan_client, borrow_payload(ids))
    assert response.status_code == (404 if invalid == "missing" else 409)
    assert snapshot(postgres_app, loan_data) == before


@pytest.mark.parametrize("invalid", ["subset", "extra", "duplicate", "bad_condition", "early_date", "missing_date", "user_id"])
def test_invalid_return_keeps_everything_borrowed(loan_client, loan_data, postgres_app, invalid):
    ids = loan_data["ids"][:2]
    loan = borrow(loan_client, borrow_payload(ids)).json
    payload = return_payload(ids)
    if invalid == "subset": payload["items"].pop()
    elif invalid == "extra": payload["items"].append({"equipment_id": loan_data["ids"][2], "condition_after": "Good"})
    elif invalid == "duplicate": payload["items"][1] = payload["items"][0].copy()
    elif invalid == "bad_condition": payload["items"][1]["condition_after"] = ""
    elif invalid == "early_date": payload["actual_return_date"] = (date.today() - timedelta(days=1)).isoformat()
    elif invalid == "missing_date": payload.pop("actual_return_date")
    else: payload["user_id"] = 12
    before = snapshot(postgres_app, loan_data)
    response = give_back(loan_client, loan["id"], payload)
    assert response.status_code == 422
    assert snapshot(postgres_app, loan_data) == before


@pytest.mark.parametrize("operation", ["create", "return"])
def test_exception_after_sql_flush_rolls_back_all_writes(loan_data, postgres_app, operation):
    ids = loan_data["ids"][:2]
    with postgres_app.app_context():
        loan_id = service.create_loan(borrow_payload(ids), actor_id=loan_data["user_id"]).id if operation == "return" else None
    before = snapshot(postgres_app, loan_data)
    flushed = []

    def fail_after_flush(session, context):
        flushed.append(True)  # SQL for all pending rows has already been sent to PostgreSQL.
        raise RuntimeError("injected failure after database writes")

    sa.event.listen(Session, "after_flush", fail_after_flush)
    try:
        with postgres_app.app_context(), pytest.raises(RuntimeError, match="injected failure"):
            if operation == "create":
                service.create_loan(borrow_payload(ids), actor_id=loan_data["user_id"])
            else:
                service.return_loan(loan_id, return_payload(ids))
    finally:
        sa.event.remove(Session, "after_flush", fail_after_flush)
    assert flushed
    assert snapshot(postgres_app, loan_data) == before
    # A fresh request can acquire the released locks and complete successfully.
    with postgres_app.app_context():
        result = (service.create_loan(borrow_payload(ids), actor_id=loan_data["user_id"]) if operation == "create"
                  else service.return_loan(loan_id, return_payload(ids)))
        assert result.status == ("BORROWED" if operation == "create" else "RETURNED")


def test_return_rejects_inconsistent_equipment_state(loan_client, loan_data, postgres_app):
    ids = loan_data["ids"][:2]
    loan = borrow(loan_client, borrow_payload(ids)).json
    with postgres_app.app_context():
        db.session.get(Equipment, ids[1]).status = "MAINTENANCE"
        db.session.commit()
    before = snapshot(postgres_app, loan_data)
    response = give_back(loan_client, loan["id"], return_payload(ids))
    assert response.status_code == 409 and response.json["error"]["code"] == "equipment_state_conflict"
    assert snapshot(postgres_app, loan_data) == before


@pytest.mark.parametrize("days", [-1, 0, 1])
def test_overdue_is_derived_and_disappears_on_return(loan_client, loan_data, days):
    payload = borrow_payload(loan_data["ids"][:1])
    payload["loan_date"] = (date.today() - timedelta(days=2)).isoformat()
    payload["expected_return_date"] = (date.today() + timedelta(days=days)).isoformat()
    loan = borrow(loan_client, payload).json
    assert loan["is_overdue"] is (days < 0)
    page = loan_client.get(f"/loans/{loan['id']}").get_data(as_text=True)
    assert ('class="badge overdue"' in page) is (days < 0)
    result = give_back(loan_client, loan["id"], return_payload(loan_data["ids"][:1]))
    assert result.json["is_overdue"] is False
    page = loan_client.get(f"/loans/{loan['id']}").get_data(as_text=True)
    assert 'class="badge overdue"' not in page and "Xác nhận trả toàn bộ phiếu" not in page


def test_web_multiple_equipment_create_return_and_owner(loan_client, loan_data):
    ids = loan_data["ids"][:2]
    assert loan_client.get("/loans").status_code == 200
    page = loan_client.get("/loans/new").get_data(as_text=True)
    assert "Thiết bị sẵn sàng" in page and all(f'value="{i}"' in page for i in ids)
    data = MultiDict([("csrf_token", csrf(loan_client)), ("loan_date", date.today().isoformat()),
                      ("expected_return_date", date.today().isoformat()), ("note", "<script>bad()</script>"),
                      ("user_id", "999999")])
    for i in ids:
        data.add("equipment_ids", str(i))
        data.add(f"condition_before_{i}", "Tốt")
    response = loan_client.post("/loans/new", data=data)
    assert response.status_code == 303
    detail_path = response.headers["Location"]
    loan = loan_client.get("/api" + detail_path).json
    assert loan["user_id"] == loan_data["user_id"] and loan["item_count"] == 2
    page = loan_client.get(detail_path).get_data(as_text=True)
    assert "&lt;script&gt;" in page and "<script>bad()</script>" not in page
    returning = MultiDict([("csrf_token", csrf(loan_client)), ("actual_return_date", date.today().isoformat())])
    for i in ids:
        returning.add("equipment_ids", str(i))
        returning.add(f"condition_after_{i}", "Đủ phụ kiện")
    response = loan_client.post(detail_path + "/return", data=returning)
    assert response.status_code == 303
    assert loan_client.get("/api" + detail_path).json["status"] == "RETURNED"
    assert loan_client.post(detail_path + "/return", data=returning).status_code == 409


def test_web_validation_preserves_values(loan_client, loan_data):
    identifier = loan_data["ids"][0]
    data = {"csrf_token": csrf(loan_client), "loan_date": date.today().isoformat(),
            "expected_return_date": (date.today() - timedelta(days=1)).isoformat(),
            "equipment_ids": str(identifier), f"condition_before_{identifier}": "Đã kiểm tra"}
    response = loan_client.post("/loans/new", data=data)
    assert response.status_code == 422
    page = response.get_data(as_text=True)
    assert "Ngày hẹn trả không được trước ngày mượn" in page and "Đã kiểm tra" in page


def test_csrf_and_api_content_types(loan_client, loan_data, postgres_app):
    payload = borrow_payload(loan_data["ids"][:1])
    assert loan_client.post("/api/loans", json=payload).status_code == 400
    assert loan_client.post("/loans/new", data={"loan_date": date.today().isoformat()}).status_code == 400
    assert not snapshot(postgres_app, loan_data)["loans"]
    loan = borrow(loan_client, payload).json
    assert loan_client.post(f"/api/loans/{loan['id']}/return", json=return_payload(loan_data["ids"][:1])).status_code == 400
    assert loan_client.post(f"/loans/{loan['id']}/return", data={}).status_code == 400
    assert loan_client.get(f"/loans/{loan['id']}/return").status_code == 405
    for body, content_type, status in [("{bad", "application/json", 400), ("text", "text/plain", 415),
                                       (json.dumps([]), "application/json", 422)]:
        result = loan_client.post("/api/loans", data=body, content_type=content_type, headers={"X-CSRFToken": csrf(loan_client)})
        assert result.status_code == status and result.is_json


def test_missing_loan_and_invalid_pagination(loan_client):
    for loan_id in (0, 9223372036854775807, 9223372036854775808):
        assert loan_client.get(f"/api/loans/{loan_id}").status_code == 404
        assert give_back(loan_client, loan_id, {}).status_code == 404
        assert loan_client.get(f"/loans/{loan_id}").status_code == 404
    assert loan_client.get("/api/loans?page=0").status_code == 400
    assert loan_client.get("/loans?page=abc").status_code == 400


def test_another_logged_in_operator_can_return_demo_loan(loan_client, loan_data, postgres_app):
    loan = borrow(loan_client, borrow_payload(loan_data["ids"][:1])).json
    with postgres_app.app_context():
        user = User(username="operator-" + uuid4().hex, full_name="Người nhận trả")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        username = user.username
    other = login_client(postgres_app, username)
    returned = give_back(other, loan["id"], return_payload(loan_data["ids"][:1]))
    assert returned.status_code == 200 and returned.json["user_id"] == loan_data["user_id"]


def run_contending_requests(app, username, first_request, second_request, *, lock_table):
    """Hold the first transaction after a real row lock; observe PostgreSQL blocking the second."""
    clients = [login_client(app, username), login_client(app, username)]
    tokens = [csrf(client) for client in clients]
    acquired, waiting, release = Event(), Event(), Event()
    attempts = {"loan-holder": [], "loan-waiter": []}
    pids, outcomes = {}, {}
    with app.app_context():
        engine = db.engine

    def before_sql(conn, cursor, statement, parameters, context, executemany):
        name = current_thread().name
        if name not in attempts or "FOR UPDATE" not in statement:
            return
        if "FROM equipment" in statement:
            attempts[name].append(next(iter(parameters.values())))
        if name == "loan-waiter" and f"FROM {lock_table}" in statement:
            pids[name] = conn.connection.driver_connection.info.backend_pid
            waiting.set()

    def after_sql(conn, cursor, statement, parameters, context, executemany):
        if current_thread().name == "loan-holder" and "FOR UPDATE" in statement and f"FROM {lock_table}" in statement and not acquired.is_set():
            pids["loan-holder"] = conn.connection.driver_connection.info.backend_pid
            acquired.set()
            if not release.wait(10):
                raise AssertionError("Timed out waiting for contention inspection")

    def worker(index, request_spec):
        path, payload = request_spec
        try:
            response = clients[index].post(path, json=payload, headers={"X-CSRFToken": tokens[index]})
            outcomes[index] = (response.status_code, response.json)
        except BaseException as error:
            outcomes[index] = error

    threads = [Thread(target=worker, args=(0, first_request), name="loan-holder"),
               Thread(target=worker, args=(1, second_request), name="loan-waiter")]
    sa.event.listen(engine, "before_cursor_execute", before_sql)
    sa.event.listen(engine, "after_cursor_execute", after_sql)
    started = []
    try:
        threads[0].start(); started.append(threads[0])
        assert acquired.wait(5), outcomes
        threads[1].start(); started.append(threads[1])
        assert waiting.wait(5), outcomes
        assert pids["loan-holder"] != pids["loan-waiter"]
        blocked = False
        deadline = monotonic() + 5
        with engine.connect() as observer:
            while monotonic() < deadline:
                blockers = observer.execute(sa.text("SELECT pg_blocking_pids(:pid)"), {"pid": pids["loan-waiter"]}).scalar_one()
                if pids["loan-holder"] in blockers:
                    blocked = True
                    break
                sleep(0.02)
        assert blocked, "The second connection never waited for the first PostgreSQL row lock"
    finally:
        release.set()
        for thread in started:
            thread.join(timeout=10)
        sa.event.remove(engine, "before_cursor_execute", before_sql)
        sa.event.remove(engine, "after_cursor_execute", after_sql)
    assert all(not thread.is_alive() for thread in started), "Request did not finish after lock release"
    assert all(not isinstance(value, BaseException) for value in outcomes.values()), outcomes
    return outcomes, attempts


def test_concurrent_borrow_same_devices_in_reverse_order(postgres_app, loan_data):
    ids = loan_data["ids"][:2]
    outcomes, attempts = run_contending_requests(
        postgres_app, loan_data["username"], ("/api/loans", borrow_payload(ids[::-1])),
        ("/api/loans", borrow_payload(ids)), lock_table="equipment")
    assert [outcomes[i][0] for i in (0, 1)] == [201, 409]
    assert outcomes[1][1]["error"]["code"] == "equipment_unavailable"
    assert attempts["loan-holder"] == attempts["loan-waiter"] == sorted(ids)
    state = snapshot(postgres_app, loan_data)
    assert len(state["loans"]) == 1 and len(state["loans"][0][3]) == 2
    assert all(dict(state["equipment"])[i] == "BORROWED" for i in ids)


def test_rollback_releases_locks_and_waiting_borrow_succeeds(postgres_app, loan_data):
    ids = loan_data["ids"][:2]
    with postgres_app.app_context():
        db.session.get(Equipment, ids[1]).status = "MAINTENANCE"
        db.session.commit()
    outcomes, _ = run_contending_requests(
        postgres_app, loan_data["username"], ("/api/loans", borrow_payload(ids)),
        ("/api/loans", borrow_payload(ids[:1])), lock_table="equipment")
    assert [outcomes[i][0] for i in (0, 1)] == [409, 201]
    state = snapshot(postgres_app, loan_data)
    assert len(state["loans"]) == 1 and len(state["loans"][0][3]) == 1
    assert dict(state["equipment"])[ids[1]] == "MAINTENANCE"


def test_concurrent_return_runs_exactly_once(postgres_app, loan_data, loan_client):
    ids = loan_data["ids"][:2]
    loan = borrow(loan_client, borrow_payload(ids)).json
    path = f"/api/loans/{loan['id']}/return"
    second_payload = return_payload(ids)
    second_payload["items"][0]["condition_after"] = "Must not overwrite the first return"
    outcomes, attempts = run_contending_requests(
        postgres_app, loan_data["username"], (path, return_payload(ids[::-1])),
        (path, second_payload), lock_table="loans")
    assert [outcomes[i][0] for i in (0, 1)] == [200, 409]
    assert outcomes[1][1]["error"]["code"] == "already_returned"
    assert attempts["loan-holder"] == sorted(ids) and attempts["loan-waiter"] == []
    detail = loan_client.get(f"/api/loans/{loan['id']}").json
    assert all(item["condition_after"] == "Đầy đủ phụ kiện" for item in detail["items"])
    assert all(status == "AVAILABLE" for _, status in snapshot(postgres_app, loan_data)["equipment"])
