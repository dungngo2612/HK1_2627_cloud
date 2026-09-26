import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from flask_migrate import downgrade, upgrade

from equipmentdesk import create_app
from equipmentdesk.extensions import db


@pytest.fixture
def app():
    # Factory, login page and anonymous access checks do not connect to PostgreSQL.
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-never-use-in-a-real-app",
        "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://localhost/equipmentdesk_test",
        "APP_STORAGE_ROOT": "./data",
        "PORT": 8080,
    })


@pytest.fixture(scope="module")
def postgres_app():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL equipmentdesk_test database")
    parsed = sa.engine.make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "equipmentdesk_test":
        pytest.fail("TEST_DATABASE_URL must point to the dedicated equipmentdesk_test database")
    parsed = parsed.set(drivername="postgresql+psycopg")
    # Every run owns a new schema. Existing tables and data are never migrated.
    schema = "test_" + uuid4().hex
    admin_engine = sa.create_engine(parsed)
    with admin_engine.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-never-use-in-a-real-app",
        "SQLALCHEMY_DATABASE_URI": parsed,
        "SQLALCHEMY_ENGINE_OPTIONS": {"connect_args": {
            "options": f"-csearch_path={schema} -cstatement_timeout=15000 -clock_timeout=10000"
        }},
    })
    try:
        with application.app_context():
            upgrade()
            # Verify reversibility before running constraint and persistence checks.
            downgrade(revision="base")
            assert sa.inspect(db.engine).get_table_names() == ["alembic_version"]
            upgrade()
        yield application
    finally:
        with application.app_context():
            db.session.remove()
            db.engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def database(postgres_app):
    with postgres_app.app_context():
        yield db
        db.session.rollback()
