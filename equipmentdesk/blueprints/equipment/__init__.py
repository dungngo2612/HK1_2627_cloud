from flask import Blueprint, flash, redirect, render_template, request, url_for

from equipmentdesk.forms.equipment import EquipmentForm
from equipmentdesk.services import equipment as service
from equipmentdesk.services.errors import ServiceError

bp = Blueprint("equipment", __name__, url_prefix="/equipment")


@bp.get("", strict_slashes=False)
def index():
    q = request.args.get("q", "")
    pagination = service.list_equipment(q, request.args.get("page", "1"))
    return render_template("equipment/list.html", pagination=pagination, q=q)


@bp.get("/<int:equipment_id>", strict_slashes=False)
def detail(equipment_id):
    return render_template("equipment/detail.html", item=service.get_equipment(equipment_id))


def edit_form(item=None):
    form = EquipmentForm(obj=item)
    error = None
    errors = {}
    status = 200
    if form.validate_on_submit():
        try:
            saved = (service.update_equipment(item.id, form.to_payload()) if item is not None
                     else service.create_equipment(form.to_payload()))
            flash("Đã cập nhật thiết bị." if item is not None else "Đã thêm thiết bị.", "success")
            return redirect(url_for("equipment.detail", equipment_id=saved.id), code=303)
        except ServiceError as failure:
            error, errors, status = failure.message, failure.fields, failure.status
    elif form.is_submitted():
        errors, status = form.errors, 422
    return render_template("equipment/form.html", form=form, item=item,
                           error=error, errors=errors), status


@bp.route("/new", methods=["GET", "POST"])
def create():
    return edit_form()


@bp.route("/<int:equipment_id>/edit", methods=["GET", "POST"])
def edit(equipment_id):
    return edit_form(service.get_equipment(equipment_id))
