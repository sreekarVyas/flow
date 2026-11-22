import os

# Point the app at the test database before any app module reads settings.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://flow:flow_local@127.0.0.1:5432/flow_test"
)
os.environ["POLL_ENABLED"] = "false"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def migrated_db():
    """Fresh schema from Alembic migrations. Skips the DB tests when Postgres is down."""
    from alembic import command
    from alembic.config import Config

    from app.db import engine

    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except OperationalError as e:
        pytest.skip(f"test database not reachable: {e.orig}")
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(cfg, "head")
    return engine


@pytest.fixture
def session(migrated_db):
    from app.db import SessionLocal

    with migrated_db.begin() as c:
        c.execute(text("TRUNCATE transactions, raw_emails, accounts, gmail_state, splits, people RESTART IDENTITY CASCADE"))
        # Keep the seed categories and rules from migration 0002; drop what tests added.
        c.execute(text("DELETE FROM rules WHERE source = 'learned'"))
        c.execute(text("DELETE FROM categories WHERE NOT is_seed"))
    with SessionLocal() as s:
        yield s
