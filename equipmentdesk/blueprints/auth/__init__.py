from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user

from equipmentdesk.forms.auth import LoginForm
from equipmentdesk.services.auth import authenticate
from equipmentdesk.services.errors import ServiceError

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("equipment.index"))
    if request.method == "POST" and request.is_json:
        raise ServiceError("Đăng nhập yêu cầu dữ liệu biểu mẫu, không nhận JSON.",
                           status=415, code="unsupported_media_type")
    form = LoginForm()
    error = None
    status = 200
    if form.validate_on_submit():
        user = authenticate(form.username.data, form.password.data)
        if user is not None:
            session.clear()
            login_user(user, remember=False)
            return redirect(url_for("equipment.index"), code=303)
        error = "Tên đăng nhập hoặc mật khẩu không đúng."
        status = 401
    elif form.is_submitted():
        status = 422
    return render_template("auth/login.html", form=form, error=error), status


@bp.post("/logout")
def logout():
    logout_user()
    session.clear()
    flash("Bạn đã đăng xuất.", "success")
    return redirect(url_for("auth.login"), code=303)
