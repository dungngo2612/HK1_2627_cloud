import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from equipmentdesk.extensions import db
from equipmentdesk.models import Equipment, EquipmentStatus
from .errors import ServiceError

STATUS_LABELS = {
    "AVAILABLE": "Sẵn sàng",
    "BORROWED": "Đang mượn",
    "MAINTENANCE": "Bảo trì",
}
FIELDS = {"code", "name", "category", "description", "status", "location"}
TEXT_FIELDS = {
    "code": ("Mã thiết bị", 80, True),
    "name": ("Tên thiết bị", 200, True),
    "category": ("Loại thiết bị", 100, True),
    "description": ("Mô tả", 10000, False),
    "location": ("Vị trí", 200, False),
}


def validate_payload(payload, current=None):
    if not isinstance(payload, dict):
        raise ServiceError("Dữ liệu phải là một đối tượng JSON.")
    errors = {}
    values = {}
    if set(payload) - FIELDS:
        errors["_form"] = ["Có trường không được hỗ trợ: " + ", ".join(sorted(set(payload) - FIELDS))]
    for key, (label, limit, required) in TEXT_FIELDS.items():
        value = payload.get(key)
        if value is None and not required:
            values[key] = None
            continue
        if not isinstance(value, str):
            errors[key] = [f"{label} phải là chuỗi ký tự và không được bỏ trống." if required
                           else f"{label} phải là chuỗi ký tự hoặc null."]
            continue
        value = value.strip()
        if required and not value:
            errors[key] = [f"Vui lòng nhập {label.lower()}."]
        elif len(value) > limit:
            errors[key] = [f"{label} không được vượt quá {limit} ký tự."]
        elif "\x00" in value:
            errors[key] = [f"{label} chứa ký tự không hợp lệ."]
        values[key] = value or None

    status = payload.get("status", current.status if current is not None else "AVAILABLE")
    if not isinstance(status, str) or status not in STATUS_LABELS:
        errors["status"] = ["Trạng thái không hợp lệ."]
    elif status == EquipmentStatus.BORROWED and (current is None or current.status != status):
        errors["status"] = ["Chỉ nghiệp vụ mượn thiết bị mới được đặt trạng thái Đang mượn."]
    if errors:
        raise ServiceError("Vui lòng kiểm tra dữ liệu thiết bị.", fields=errors)
    if current is not None and current.status == EquipmentStatus.BORROWED and status != current.status:
        raise ServiceError("Không thể đổi trạng thái thiết bị đang mượn. Hãy thực hiện nghiệp vụ trả thiết bị.",
                           status=409, code="borrowed_equipment",
                           fields={"status": ["Thiết bị đang mượn phải giữ nguyên trạng thái."]})
    values["status"] = status
    return values


def get_equipment(equipment_id, *, lock=False):
    if not 0 < equipment_id <= 9223372036854775807:
        raise ServiceError("Không tìm thấy thiết bị.", status=404, code="not_found")
    query = sa.select(Equipment).where(Equipment.id == equipment_id)
    if lock:
        # Refresh any identity already loaded by the web view before taking the lock.
        query = query.with_for_update().execution_options(populate_existing=True)
    item = db.session.scalar(query)
    if item is None:
        raise ServiceError("Không tìm thấy thiết bị.", status=404, code="not_found")
    return item


def list_equipment(q="", page="1"):
    q = q.strip()
    if "\x00" in q:
        raise ServiceError("Từ khóa tìm kiếm chứa ký tự không hợp lệ.")
    if len(q) > 200:
        raise ServiceError("Từ khóa tìm kiếm không được vượt quá 200 ký tự.", fields={"q": ["Từ khóa quá dài."]})
    try:
        page = int(page)
        if not 1 <= page <= 1000000:
            raise ValueError
    except (ValueError, TypeError):
        raise ServiceError("Số trang phải là số nguyên từ 1 đến 1000000.", status=400, fields={"page": ["Số trang không hợp lệ."]}) from None
    query = sa.select(Equipment)
    if q:
        query = query.where(sa.or_(*(column.icontains(q, autoescape=True) for column in
                                    (Equipment.code, Equipment.name, Equipment.category, Equipment.location))))
    return db.paginate(query.order_by(Equipment.id.desc()), page=page, per_page=20, error_out=False)


def _save(item):
    try:
        db.session.add(item)
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_equipment_code":
            raise ServiceError("Mã thiết bị đã tồn tại.", status=409, code="duplicate_code",
                               fields={"code": ["Mã thiết bị đã tồn tại. Vui lòng chọn mã khác."]}) from None
        raise
    return item


def create_equipment(payload):
    return _save(Equipment(**validate_payload(payload)))


def update_equipment(equipment_id, payload):
    try:
        item = get_equipment(equipment_id, lock=True)
        values = validate_payload(payload, current=item)
        for key, value in values.items():
            setattr(item, key, value)
        return _save(item)
    except Exception:
        db.session.rollback()
        raise


def serialize_equipment(item):
    return {"id": item.id, **{key: getattr(item, key) for key in sorted(FIELDS)},
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}
