import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Point Settings at the test DB before any app module reads it — but only
# when DATABASE_URL_TEST is actually set. Never fall through to an empty
# string: an empty DATABASE_URL env var overrides both the class default
# and .env's value (pydantic-settings prioritizes process env), which would
# otherwise silently leave DATABASE_URL resolved to the real seeded dev DB.
# The db_engine fixture below has its own belt-and-suspenders check for
# that same failure mode (asserting the DB name ends in `_test`), since
# table-truncating fixtures pointed at the wrong DB would destroy real data.
_test_db_url = os.environ.get("DATABASE_URL_TEST")
if _test_db_url:
    os.environ["DATABASE_URL"] = _test_db_url

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
    # Belt-and-suspenders against the "silently wipes the real dev DB"
    # failure mode: db_session below truncates every table after each test,
    # so refuse to even connect unless the DB name is unmistakably a test DB.
    db_name = settings.database_url.rsplit("/", 1)[-1]
    if not db_name.endswith("_test"):
        raise RuntimeError(
            f"DATABASE_URL resolves to {db_name!r}, which doesn't look like a "
            "test database (expected a name ending in '_test'). Refusing to "
            "run table-truncating fixtures against it — export DATABASE_URL_TEST "
            "pointing at a disposable *_test database before running tests."
        )

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
