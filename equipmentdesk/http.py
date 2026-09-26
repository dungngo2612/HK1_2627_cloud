from flask import current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .extensions import db, login_manager
from .services.equipment import STATUS_LABELS
from .services.errors import ServiceError


def is_api_request():
    return request.path == "/api" or request.path.startswith("/api/")


def error_response(message, status, code, fields=None):
    if is_api_request():
        return jsonify(error={"code": code, "message": message, "fields": fields or {}}), status
    return render_template("error.html", message=message, status=status, hide_navigation=(status == 503)), status


def register_access_control(app):
    @login_manager.unauthorized_handler
    def unauthorized():
        if is_api_request():
            return error_response("Vui lòng đăng nhập để sử dụng API.", 401, "authentication_required")
        return redirect(url_for("auth.login"))

    # Register before CSRFProtect: anonymous API mutations must return JSON 401.
    @app.before_request
    def require_authentication():
        if request.endpoint in {"auth.login", "api.csrf_token", "static", "health.live", "health.ready"}:
            return None
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if (request.is_json and request.content_length is not None
                and request.content_length > current_app.config["MAX_JSON_CONTENT_LENGTH"]):
            raise RequestEntityTooLarge()
        return None

    @app.after_request
    def prevent_private_response_cache(response):
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.context_processor
    def template_helpers():
        return {"status_labels": STATUS_LABELS, "current_user": current_user}


def register_error_handlers(app):
    @app.errorhandler(CSRFError)
    def csrf_failure(error):
        return error_response("Mã CSRF thiếu, không hợp lệ hoặc đã hết hạn. Vui lòng tải lại trang hoặc lấy token mới.",
                              400, "csrf_error")

    @app.errorhandler(ServiceError)
    def service_failure(error):
        return error_response(error.message, error.status, error.code, error.fields)

    @app.errorhandler(HTTPException)
    def http_failure(error):
        messages = {
            400: "Yêu cầu không hợp lệ. Hãy kiểm tra định dạng JSON và dữ liệu gửi lên.",
            404: "Không tìm thấy trang hoặc tài nguyên.",
            405: "Phương thức HTTP không được hỗ trợ.",
            413: "Dữ liệu gửi lên quá lớn.",
            415: "API yêu cầu Content-Type: application/json.",
        }
        response = app.make_response(error_response(messages.get(error.code, "Không thể xử lý yêu cầu."),
                                                     error.code, f"http_{error.code}"))
        if error.code == 405:
            response.headers["Allow"] = ", ".join(error.valid_methods or [])
        return response

    @app.errorhandler(SQLAlchemyError)
    def database_failure(error):
        db.session.rollback()
        app.logger.error("Database request failed: %s", type(error).__name__)
        return error_response("Không thể truy cập database. Vui lòng kiểm tra kết nối và migration.",
                              503, "database_unavailable")
