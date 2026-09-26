from flask import Blueprint, current_app, jsonify
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from equipmentdesk.extensions import db
from equipmentdesk.storage.local import LocalStorage

bp = Blueprint("health", __name__)


@bp.get("/health/live")
def live():
    return jsonify(status="ok", database="not_checked", storage="not_checked"), 200


@bp.get("/health/ready")
def ready():
    database_status = "ok"
    storage_status = "ok"
    try:
        db.session.execute(sa.text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        db.session.rollback()
        database_status = "error"

    try:
        LocalStorage(current_app.config["APP_STORAGE_ROOT"]).probe()
    except OSError:
        storage_status = "error"

    overall = "ok" if database_status == storage_status == "ok" else "not_ready"
    status_code = 200 if overall == "ok" else 503
    return jsonify(status=overall, database=database_status, storage=storage_status), status_code
