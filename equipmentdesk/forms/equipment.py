from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField

from equipmentdesk.services.equipment import STATUS_LABELS


class EquipmentForm(FlaskForm):
    # Business validation is shared with JSON API in services.equipment.
    code = StringField("Mã thiết bị")
    name = StringField("Tên thiết bị")
    category = StringField("Loại thiết bị")
    description = TextAreaField("Mô tả")
    location = StringField("Vị trí")
    status = SelectField("Trạng thái", default="AVAILABLE", validate_choice=False,
                         choices=[(key, STATUS_LABELS[key]) for key in ("AVAILABLE", "MAINTENANCE")])
    submit = SubmitField("Lưu thiết bị")

    def to_payload(self):
        values = {key: self[key].data for key in ("code", "name", "category", "description", "location")}
        if self.status.raw_data:
            values["status"] = self.status.data
        return values
