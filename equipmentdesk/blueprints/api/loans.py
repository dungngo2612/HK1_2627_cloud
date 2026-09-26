from flask import Blueprint, jsonify, request, url_for
from flask_login import current_user

from equipmentdesk.services import loans as service
from equipmentdesk.services import attachments as attachment_service

bp = Blueprint("loans_api", __name__, url_prefix="/api/loans")


@bp.get("", strict_slashes=False)
def index():
    result = service.list_loans(request.args.get("page", "1"))
    return jsonify(items=[service.serialize_loan(loan, include_items=False) for loan in result.items],
                   page=result.page, per_page=result.per_page, total=result.total, pages=result.pages)


@bp.get("/<int:loan_id>", strict_slashes=False)
def detail(loan_id):
    return jsonify(service.serialize_loan(service.get_loan(loan_id)))


@bp.post("", strict_slashes=False)
def create():
    loan = service.create_loan(request.get_json(), actor_id=current_user.id)
    response = jsonify(service.serialize_loan(loan))
    response.status_code = 201
    response.headers["Location"] = url_for("loans_api.detail", loan_id=loan.id)
    return response


@bp.post("/<int:loan_id>/return", strict_slashes=False)
def return_all(loan_id):
    return jsonify(service.serialize_loan(service.return_loan(loan_id, request.get_json())))


@bp.post("/<int:loan_id>/attachments", strict_slashes=False)
def upload_attachment(loan_id):
    attachment = attachment_service.create_attachment(loan_id, request.files.get("file"))
    response = jsonify(attachment_service.serialize_attachment(attachment))
    response.status_code = 201
    response.headers["Location"] = url_for("attachments_api.detail", attachment_id=attachment.id)
    return response
