from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import InputRequired, Length


class LoginForm(FlaskForm):
    username = StringField("Tên đăng nhập", validators=[InputRequired(message="Vui lòng nhập tên đăng nhập."),
                            Length(max=80, message="Tên đăng nhập tối đa 80 ký tự.")])
    password = PasswordField("Mật khẩu", validators=[InputRequired(message="Vui lòng nhập mật khẩu."),
                              Length(max=128, message="Mật khẩu tối đa 128 ký tự.")])
    submit = SubmitField("Đăng nhập")
