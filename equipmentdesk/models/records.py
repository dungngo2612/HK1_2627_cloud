from datetime import date
from uuid import uuid4

import sqlalchemy as sa
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from equipmentdesk.extensions import db
from .enums import EquipmentStatus, LoanStatus


class CreatedAtMixin:
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class TimestampMixin(CreatedAtMixin):
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
                           onupdate=sa.func.now(), server_onupdate=sa.FetchedValue())


class User(UserMixin, CreatedAtMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.BigInteger, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(160), nullable=False)
    loans = db.relationship("Loan", back_populates="user", passive_deletes="all")
    __table_args__ = (
        db.CheckConstraint("length(trim(username)) > 0", name="username_not_blank"),
        db.CheckConstraint("length(trim(full_name)) > 0", name="full_name_not_blank"),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Equipment(TimestampMixin, db.Model):
    __tablename__ = "equipment"
    id = db.Column(db.BigInteger, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default=EquipmentStatus.AVAILABLE,
                       server_default="AVAILABLE")
    location = db.Column(db.String(200))
    loan_items = db.relationship("LoanItem", back_populates="equipment", passive_deletes="all")
    __table_args__ = (
        db.CheckConstraint("status IN ('AVAILABLE', 'BORROWED', 'MAINTENANCE')", name="valid_status"),
        db.CheckConstraint("length(trim(code)) > 0", name="code_not_blank"),
        db.CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        db.CheckConstraint("length(trim(category)) > 0", name="category_not_blank"),
    )


class Loan(TimestampMixin, db.Model):
    __tablename__ = "loans"
    id = db.Column(db.BigInteger, primary_key=True)
    loan_code = db.Column(db.String(80), nullable=False, unique=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    loan_date = db.Column(db.Date, nullable=False)
    expected_return_date = db.Column(db.Date, nullable=False)
    actual_return_date = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default=LoanStatus.BORROWED, server_default="BORROWED")
    note = db.Column(db.Text)
    user = db.relationship("User", back_populates="loans")
    items = db.relationship("LoanItem", back_populates="loan", passive_deletes="all")
    attachments = db.relationship("Attachment", back_populates="loan", passive_deletes="all")
    __table_args__ = (
        db.CheckConstraint("length(trim(loan_code)) > 0", name="loan_code_not_blank"),
        db.CheckConstraint("status IN ('BORROWED', 'RETURNED')", name="valid_status"),
        db.CheckConstraint("expected_return_date >= loan_date", name="expected_return_date"),
        db.CheckConstraint("actual_return_date IS NULL OR actual_return_date >= loan_date", name="actual_return_date"),
        db.CheckConstraint("(status = 'BORROWED' AND actual_return_date IS NULL) OR "
                           "(status = 'RETURNED' AND actual_return_date IS NOT NULL)", name="return_state"),
    )

    def is_overdue_on(self, on_date):
        return self.status == LoanStatus.BORROWED and self.expected_return_date < on_date

    @property
    def is_overdue(self):
        return self.is_overdue_on(date.today())


class LoanItem(db.Model):
    __tablename__ = "loan_items"
    id = db.Column(db.BigInteger, primary_key=True)
    loan_id = db.Column(db.BigInteger, db.ForeignKey("loans.id", ondelete="RESTRICT"), nullable=False)
    equipment_id = db.Column(db.BigInteger, db.ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False, index=True)
    condition_before = db.Column(db.Text, nullable=False)
    condition_after = db.Column(db.Text)
    loan = db.relationship("Loan", back_populates="items")
    equipment = db.relationship("Equipment", back_populates="loan_items")
    __table_args__ = (
        db.UniqueConstraint("loan_id", "equipment_id", name="uq_loan_items_loan_equipment"),
        db.CheckConstraint("length(trim(condition_before)) > 0", name="condition_before_not_blank"),
    )


class Attachment(CreatedAtMixin, db.Model):
    __tablename__ = "attachments"
    id = db.Column(sa.Uuid, primary_key=True, default=uuid4)
    loan_id = db.Column(db.BigInteger, db.ForeignKey("loans.id", ondelete="RESTRICT"), nullable=False, index=True)
    relative_path = db.Column(db.String(1024), nullable=False, unique=True)
    original_name = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(255), nullable=False)
    size = db.Column(db.BigInteger, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    loan = db.relationship("Loan", back_populates="attachments")
    __table_args__ = (
        db.CheckConstraint("size >= 0", name="nonnegative_size"),
        db.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="valid_sha256"),
        db.CheckConstraint("length(trim(original_name)) > 0", name="original_name_not_blank"),
        db.CheckConstraint("length(trim(content_type)) > 0", name="content_type_not_blank"),
        db.CheckConstraint("length(relative_path) > 0 AND relative_path !~ '^/' "
                           "AND relative_path !~ '(^|/)[.]{1,2}(/|$)' "
                           "AND position(chr(92) in relative_path) = 0 "
                           "AND position(':' in relative_path) = 0", name="relative_path"),
    )
