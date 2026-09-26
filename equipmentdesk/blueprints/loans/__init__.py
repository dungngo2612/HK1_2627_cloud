from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from equipmentdesk.forms.loans import LoanForm, ReturnLoanForm
from equipmentdesk.forms.attachments import AttachmentForm
from equipmentdesk.services import loans as service
from equipmentdesk.services import attachments as attachment_service
from equipmentdesk.services.errors import ServiceError

bp = Blueprint("loans", __name__, url_prefix="/loans")


@bp.get("", strict_slashes=False)
def index():
    return render_template("loans/list.html", pagination=service.list_loans(request.args.get("page", "1")))


@bp.get("/<int:loan_id>", strict_slashes=False)
def detail(loan_id):
    return render_template("loans/detail.html", loan=service.get_loan(loan_id),
                           form=ReturnLoanForm(), upload_form=AttachmentForm(), errors={}, error=None,
                           upload_errors={}, upload_error=None)


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = LoanForm()
    error, errors, status = None, {}, 200
    if form.validate_on_submit():
        try:
            loan = service.create_loan(form.to_payload(request.form), actor_id=current_user.id)
            flash("Đã tạo phiếu mượn và cập nhật trạng thái thiết bị.", "success")
            return redirect(url_for("loans.detail", loan_id=loan.id), code=303)
        except ServiceError as failure:
            error, errors, status = failure.message, failure.fields, failure.status
    elif form.is_submitted():
        errors, status = form.errors, 422
    return render_template("loans/form.html", form=form, error=error, errors=errors,
                           equipment=service.available_equipment(), selected=request.form.getlist("equipment_ids")), status


@bp.post("/<int:loan_id>/return", strict_slashes=False)
def return_all(loan_id):
    form = ReturnLoanForm()
    error, errors, status = None, {}, 422
    if form.validate_on_submit():
        try:
            loan = service.return_loan(loan_id, form.to_payload(request.form))
            flash("Đã trả toàn bộ phiếu và cập nhật thiết bị về Sẵn sàng.", "success")
            return redirect(url_for("loans.detail", loan_id=loan.id), code=303)
        except ServiceError as failure:
            error, errors, status = failure.message, failure.fields, failure.status
    else:
        errors = form.errors
    return render_template("loans/detail.html", loan=service.get_loan(loan_id),
                           form=form, upload_form=AttachmentForm(), error=error, errors=errors,
                           upload_errors={}, upload_error=None), status


@bp.post("/<int:loan_id>/attachments", strict_slashes=False)
def upload_attachment(loan_id):
    form = AttachmentForm()
    upload_error, upload_errors, status = None, {}, 422
    if form.validate_on_submit():
        try:
            attachment_service.create_attachment(loan_id, form.file.data)
            flash("Đã tải biên bản lên phiếu mượn.", "success")
            return redirect(url_for("loans.detail", loan_id=loan_id), code=303)
        except ServiceError as failure:
            upload_error, upload_errors, status = failure.message, failure.fields, failure.status
    else:
        upload_errors = form.errors
    return render_template("loans/detail.html", loan=service.get_loan(loan_id),
                           form=ReturnLoanForm(), upload_form=form, error=None, errors={},
                           upload_error=upload_error, upload_errors=upload_errors), status
