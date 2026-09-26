import os

import click
from sqlalchemy.exc import SQLAlchemyError

from .extensions import db
from .services.auth import create_demo_user
from .services.errors import ServiceError
from .services.seed import seed_demo_data


def register_cli(app):
    @app.cli.command("create-demo-user")
    def create_demo_user_command():
        """Create a demo user from DEMO_USERNAME and DEMO_PASSWORD, without overwriting."""
        try:
            created = create_demo_user(os.getenv("DEMO_USERNAME"), os.getenv("DEMO_PASSWORD"))
        except ServiceError as error:
            raise click.ClickException(error.message) from None
        except SQLAlchemyError:
            db.session.rollback()
            raise click.ClickException("Không thể truy cập database. Kiểm tra cấu hình và chạy migration trước.") from None
        click.echo("Đã tạo user demo." if created else "User đã tồn tại; giữ nguyên thông tin và mật khẩu.")

    @app.cli.command("seed-demo-data")
    def seed_demo_data_command():
        """Seed example users, equipment, loans and attachments; never runs at app startup."""
        try:
            result = seed_demo_data(os.getenv("DEMO_USERNAME"), os.getenv("DEMO_PASSWORD"))
        except ServiceError as error:
            db.session.rollback()
            raise click.ClickException(error.message) from None
        except SQLAlchemyError:
            db.session.rollback()
            raise click.ClickException("Không thể truy cập database. Chạy migration và kiểm tra kết nối trước.") from None
        click.echo(
            "Seed hoàn tất: "
            f"user {'mới' if result['user_created'] else 'đã có'}, "
            f"{result['equipment_created']} thiết bị mới, "
            f"{result['loans_created']} phiếu mới, "
            f"{result['attachments_created']} file mới."
        )
        if result["skipped_loans"]:
            click.echo("Bỏ qua phiếu do mã thiết bị mẫu đã có trạng thái khác: "
                       + ", ".join(result["skipped_loans"]))
