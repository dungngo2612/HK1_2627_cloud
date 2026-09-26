from datetime import date

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField


def form_equipment_id(raw):
    # JSON IDs must be integers. HTML form values are strings; convert only decimal IDs.
    try:
        return int(raw) if raw.isascii() and raw.isdecimal() else raw
    except (ValueError, AttributeError):
        return raw


class LoanForm(FlaskForm):
    loan_date = StringField("Ngày mượn", default=lambda: date.today().isoformat())
    expected_return_date = StringField("Ngày hẹn trả", default=lambda: date.today().isoformat())
    note = TextAreaField("Ghi chú")
    submit = SubmitField("Tạo phiếu mượn")

    def to_payload(self, data):
        return {"loan_date": self.loan_date.data, "expected_return_date": self.expected_return_date.data,
                "note": self.note.data,
                "items": [{"equipment_id": form_equipment_id(raw),
                           "condition_before": data.get("condition_before_" + raw, "")}
                          for raw in data.getlist("equipment_ids")]}


class ReturnLoanForm(FlaskForm):
    actual_return_date = StringField("Ngày trả", default=lambda: date.today().isoformat())
    submit = SubmitField("Xác nhận trả toàn bộ phiếu")

    def to_payload(self, data):
        return {"actual_return_date": self.actual_return_date.data,
                "items": [{"equipment_id": form_equipment_id(raw),
                           "condition_after": data.get("condition_after_" + raw, "")}
                          for raw in data.getlist("equipment_ids")]}
