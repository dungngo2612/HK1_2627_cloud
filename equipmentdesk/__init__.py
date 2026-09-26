from flask import Flask

from .config import PROJECT_ROOT, load_config, validate_config
from .extensions import csrf, db, login_manager, migrate


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(load_config())
    if test_config is not None:
        app.config.update(test_config)
    validate_config(app.config)

    db.init_app(app)
    from . import models  # Register all tables for Alembic metadata.

    migrate.init_app(app, db, directory=str(PROJECT_ROOT / "migrations"))
    # Templates resolve current_user lazily so a DB outage can still render an error page.
    login_manager.init_app(app, add_context_processor=False)
    from .http import register_access_control, register_error_handlers
    register_access_control(app)
    csrf.init_app(app)
    register_error_handlers(app)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            identifier = int(user_id)
        except (TypeError, ValueError):
            return None
        if not 0 < identifier <= 9223372036854775807:
            return None
        return db.session.get(models.User, identifier)

    from .blueprints.main import bp as main_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.equipment import bp as equipment_bp
    from .blueprints.api import bp as api_bp
    from .blueprints.loans import bp as loans_bp
    from .blueprints.api.loans import bp as loans_api_bp
    from .blueprints.api.attachments import bp as attachments_api_bp
    from .blueprints.health import bp as health_bp
    for blueprint in (main_bp, auth_bp, equipment_bp, api_bp, loans_bp, loans_api_bp, attachments_api_bp,
                      health_bp):
        app.register_blueprint(blueprint)
    from .cli import register_cli
    register_cli(app)
    return app
