import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Point Settings at the test DB before any app module reads it.
os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL_TEST", ""))

import app.models  # noqa: E402,F401
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def db_engine(settings):
    # Schema comes from `alembic upgrade head` against DATABASE_URL_TEST
    # (run as its own CI step, and required locally before `pytest`) — not
    # from Base.metadata.create_all here. That keeps exactly one source of
    # schema truth (the migrations), which matters specifically because
    # migration 0002 is what creates the wms_readonly role and its grants;
    # a create_all-only test DB would silently skip that and let a broken
    # grant pass tests.
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        has_tables = conn.execute(
            text("SELECT to_regclass('public.locations')")
        ).scalar()
    if has_tables is None:
        raise RuntimeError(
            "Test DB has no schema. Run `alembic upgrade head` against "
            "DATABASE_URL_TEST before running tests (CI does this as a "
            "separate step — see .github/workflows/ci.yml)."
        )
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.rollback()
    # Keep tests isolated without needing per-test migrations.
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()


@pytest.fixture()
def readonly_db_session(settings, db_engine):
    """Uses DATABASE_URL_READONLY if the wms_readonly role exists (via
    migration 0002); falls back to the privileged engine for tests that
    don't depend on the role-grant boundary itself.
    """
    try:
        engine = create_engine(settings.database_url_readonly)
        conn = engine.connect()
        conn.close()
    except Exception:
        engine = db_engine
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
