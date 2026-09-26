import secrets

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from equipmentdesk.extensions import db
from equipmentdesk.models import User
from .errors import ServiceError

# An unknown username still performs a password hash check.
_DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(32))


def authenticate(username, password):
    user = db.session.scalar(sa.select(User).where(User.username == username.strip()))
    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        return None
    return user if user.check_password(password) else None


def create_demo_user(username, password):
    if not username or not username.strip() or len(username.strip()) > 80 or "\x00" in username:
        raise ServiceError("DEMO_USERNAME phải có từ 1 đến 80 ký tự hợp lệ.")
    if not password:
        raise ServiceError("Vui lòng đặt DEMO_PASSWORD trong môi trường.")
    username = username.strip()
    existing = db.session.scalar(sa.select(User).where(User.username == username))
    if existing is not None:
        return False
    if not 8 <= len(password) <= 128 or not password.strip():
        raise ServiceError("DEMO_PASSWORD cho user mới phải có từ 8 đến 128 ký tự, không chỉ chứa khoảng trắng.")
    user = User(username=username, full_name=username)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_users_username":
            return False  # Another invocation already created this username.
        raise
    return True
