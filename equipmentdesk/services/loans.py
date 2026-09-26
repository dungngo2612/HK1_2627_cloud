from datetime import date
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import selectinload

from equipmentdesk.extensions import db
from equipmentdesk.models import Equipment, EquipmentStatus, Loan, LoanItem, LoanStatus
from .errors import ServiceError

MAX_ITEMS = 100
MAX_ID = 9223372036854775807


def _error(message, field):
    raise ServiceError(message, fields={field: [message]})


def _object(payload, allowed, field="_form"):
    if not isinstance(payload, dict):
        _error("Dữ liệu phải là một đối tượng JSON.", field)
    if set(payload) - allowed:
        _error("Có trường không được hỗ trợ: " + ", ".join(sorted(set(payload) - allowed)), field)


def _date(value, field, label):
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError:
        _error(f"{label} phải là ngày hợp lệ theo định dạng YYYY-MM-DD.", field)


def _text(value, field, label, limit, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        _error(f"{label} phải là chuỗi ký tự.", field)
    value = value.strip()
    if (required and not value) or len(value) > limit or "\x00" in value:
        _error(f"{label} phải có từ {1 if required else 0} đến {limit} ký tự hợp lệ.", field)
    return value or None


def _items(payload, condition_field):
    items = payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        _error(f"Phiếu phải có từ 1 đến {MAX_ITEMS} thiết bị.", "items")
    normalized = {}
    for index, item in enumerate(items):
        field = f"items.{index}"
        _object(item, {"equipment_id", condition_field}, field)
        identifier = item.get("equipment_id")
        if type(identifier) is not int or not 0 < identifier <= MAX_ID:
            _error("ID thiết bị phải là số nguyên dương hợp lệ.", field + ".equipment_id")
        if identifier in normalized:
            _error("Không được lặp thiết bị trong cùng một phiếu.", "items")
        normalized[identifier] = _text(item.get(condition_field), field + "." + condition_field,
                                       "Tình trạng thiết bị", 2000)
    return normalized


def _lock_equipment(identifiers):
    """Acquire every physical device lock in ascending ID order in this transaction."""
    equipment = {}
    for identifier in sorted(identifiers):
        row = db.session.scalar(sa.select(Equipment).where(Equipment.id == identifier)
                                .with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise ServiceError(f"Không tìm thấy thiết bị ID {identifier}.", status=404, code="equipment_not_found")
        equipment[identifier] = row
    return equipment


def create_loan(payload, *, actor_id):
    """actor_id must come from the authenticated session, never the request body.

    The scoped session may already have a read transaction from Flask-Login. Use
    that same transaction for locks and writes, committing once at the very end.
    """
    try:
        _object(payload, {"loan_date", "expected_return_date", "note", "items"})
        loan_date = _date(payload.get("loan_date"), "loan_date", "Ngày mượn")
        expected = _date(payload.get("expected_return_date"), "expected_return_date", "Ngày hẹn trả")
        if expected < loan_date:
            _error("Ngày hẹn trả không được trước ngày mượn.", "expected_return_date")
        note = _text(payload.get("note"), "note", "Ghi chú", 10000, required=False)
        conditions = _items(payload, "condition_before")
        equipment = _lock_equipment(conditions)
        for item in equipment.values():
            if item.status != EquipmentStatus.AVAILABLE:
                raise ServiceError(f"Thiết bị {item.code} không ở trạng thái Sẵn sàng.",
                                   status=409, code="equipment_unavailable", fields={"items": [f"{item.code} không thể mượn."]})
        loan = Loan(loan_code=f"PM-{loan_date:%Y%m%d}-{uuid4().hex}", user_id=actor_id,
                    loan_date=loan_date, expected_return_date=expected,
                    status=LoanStatus.BORROWED, note=note)
        db.session.add(loan)
        for identifier, item in equipment.items():
            db.session.add(LoanItem(loan=loan, equipment=item, condition_before=conditions[identifier]))
            item.status = EquipmentStatus.BORROWED
        db.session.commit()
        return loan
    except Exception:
        db.session.rollback()
        raise


def get_loan(loan_id, *, lock=False):
    if not 0 < loan_id <= MAX_ID:
        raise ServiceError("Không tìm thấy phiếu mượn.", status=404, code="not_found")
    query = sa.select(Loan).where(Loan.id == loan_id)
    if lock:
        # Do not join user/items into a FOR UPDATE query: only lock the loan here.
        query = query.with_for_update().execution_options(populate_existing=True)
    else:
        query = query.options(selectinload(Loan.user), selectinload(Loan.items).selectinload(LoanItem.equipment))
    loan = db.session.scalar(query)
    if loan is None:
        raise ServiceError("Không tìm thấy phiếu mượn.", status=404, code="not_found")
    return loan


def return_loan(loan_id, payload):
    try:
        # Serialize returns on this loan before reading its current state/items.
        loan = get_loan(loan_id, lock=True)
        if loan.status == LoanStatus.RETURNED:
            raise ServiceError("Phiếu đã được trả, không thể trả lần thứ hai.", status=409, code="already_returned")
        _object(payload, {"actual_return_date", "items"})
        returned_on = _date(payload.get("actual_return_date"), "actual_return_date", "Ngày trả")
        if returned_on < loan.loan_date:
            _error("Ngày trả không được trước ngày mượn.", "actual_return_date")
        conditions = _items(payload, "condition_after")
        loan_items = db.session.scalars(sa.select(LoanItem).where(LoanItem.loan_id == loan.id)
                                       .order_by(LoanItem.equipment_id)
                                       .execution_options(populate_existing=True)).all()
        if set(conditions) != {item.equipment_id for item in loan_items}:
            _error("Phải trả đủ và đúng tất cả thiết bị của phiếu, không thêm thiết bị khác.", "items")
        equipment = _lock_equipment(conditions)
        for row in equipment.values():
            if row.status != EquipmentStatus.BORROWED:
                raise ServiceError(f"Trạng thái thiết bị {row.code} không khớp phiếu đang mượn.",
                                   status=409, code="equipment_state_conflict")
        for item in loan_items:
            item.condition_after = conditions[item.equipment_id]
            equipment[item.equipment_id].status = EquipmentStatus.AVAILABLE
        loan.actual_return_date = returned_on
        loan.status = LoanStatus.RETURNED
        db.session.commit()
        return loan
    except Exception:
        db.session.rollback()
        raise


def list_loans(page="1"):
    try:
        page = int(page)
        if not 1 <= page <= 1000000:
            raise ValueError
    except (ValueError, TypeError):
        raise ServiceError("Số trang phải là số nguyên từ 1 đến 1000000.", status=400, fields={"page": ["Số trang không hợp lệ."]}) from None
    query = sa.select(Loan).options(selectinload(Loan.user), selectinload(Loan.items)).order_by(Loan.id.desc())
    return db.paginate(query, page=page, per_page=20, error_out=False)


def available_equipment():
    return db.session.scalars(sa.select(Equipment).where(Equipment.status == EquipmentStatus.AVAILABLE)
                              .order_by(Equipment.code)).all()


def serialize_loan(loan, *, include_items=True):
    result = {
        "id": loan.id, "loan_code": loan.loan_code, "user_id": loan.user_id,
        "user": {"id": loan.user.id, "username": loan.user.username, "full_name": loan.user.full_name},
        "loan_date": loan.loan_date.isoformat(), "expected_return_date": loan.expected_return_date.isoformat(),
        "actual_return_date": loan.actual_return_date.isoformat() if loan.actual_return_date else None,
        "status": loan.status, "is_overdue": loan.is_overdue, "note": loan.note,
        "created_at": loan.created_at.isoformat(), "updated_at": loan.updated_at.isoformat(),
        "item_count": len(loan.items),
    }
    if include_items:
        result["items"] = [{"id": item.id, "equipment_id": item.equipment_id,
                            "code": item.equipment.code, "name": item.equipment.name,
                            "condition_before": item.condition_before, "condition_after": item.condition_after}
                           for item in sorted(loan.items, key=lambda item: item.equipment_id)]
    return result
