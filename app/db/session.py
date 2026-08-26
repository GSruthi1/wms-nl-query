"""
Two separate SQLAlchemy engines, deliberately not one.

`engine` (privileged): runs Alembic migrations and writes `audit_log` rows.
Used by the app for everything except executing LLM-generated SQL.

`readonly_engine`: the ONLY engine that ever executes SQL text produced by
the LLM. It authenticates as `wms_readonly`, a Postgres role granted SELECT
on the WMS data tables only (not `audit_log` — see
alembic/versions/0002_readonly_role.py). Every connection also gets a
session-level `statement_timeout` so a slow/expensive generated query can't
hang the DB. This is a deliberate second layer of defense underneath the
app-level SQL validator (app/nl2sql/validator.py): even a validator bug or
bypass still can't write data or read the audit trail, because the DB
grants don't allow it.
"""
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

readonly_engine = create_engine(settings.database_url_readonly, pool_pre_ping=True)
ReadOnlySessionLocal = sessionmaker(bind=readonly_engine, autoflush=False, autocommit=False)


@event.listens_for(readonly_engine, "connect")
def _set_statement_timeout(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute(f"SET statement_timeout = {settings.sql_statement_timeout_ms}")
    cursor.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: privileged session (audit writes, non-generated-SQL reads)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_readonly_db() -> Generator[Session, None, None]:
    """FastAPI dependency: read-only session for executing LLM-generated SQL only."""
    db = ReadOnlySessionLocal()
    try:
        yield db
    finally:
        db.close()
