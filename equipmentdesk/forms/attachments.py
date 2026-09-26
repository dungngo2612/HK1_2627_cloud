from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import SubmitField


class AttachmentForm(FlaskForm):
    file = FileField("Biên bản (PDF, PNG hoặc JPEG; tối đa 10 MB)",
                     validators=[FileRequired(message="Vui lòng chọn file biên bản.")])
    submit = SubmitField("Tải biên bản lên")
