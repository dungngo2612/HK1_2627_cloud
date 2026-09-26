from flask import Blueprint, jsonify, request, url_for
from flask_wtf.csrf import generate_csrf

from equipmentdesk.services import equipment as service

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.get("/csrf-token")
def csrf_token():
    # Public: this establishes the session required to submit the login form.
    return jsonify(csrf_token=generate_csrf())


@bp.get("/equipment", strict_slashes=False)
def index():
    result = service.list_equipment(request.args.get("q", ""), request.args.get("page", "1"))
    return jsonify(items=[service.serialize_equipment(item) for item in result.items],
                   page=result.page, per_page=result.per_page, total=result.total, pages=result.pages)


@bp.post("/equipment", strict_slashes=False)
def create():
    item = service.create_equipment(request.get_json())
    response = jsonify(service.serialize_equipment(item))
    response.status_code = 201
    response.headers["Location"] = url_for("api.detail", equipment_id=item.id)
    return response


@bp.get("/equipment/<int:equipment_id>", strict_slashes=False)
def detail(equipment_id):
    return jsonify(service.serialize_equipment(service.get_equipment(equipment_id)))


@bp.put("/equipment/<int:equipment_id>", strict_slashes=False)
def update(equipment_id):
    item = service.update_equipment(equipment_id, request.get_json())
    return jsonify(service.serialize_equipment(item))
