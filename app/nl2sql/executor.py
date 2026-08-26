"""Executes validated SQL against the read-only role's connection."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class ExecutionResult:
    success: bool
    columns: list[str]
    rows: list[dict]
    row_count: int
    error: str | None = None


def _json_safe(value):
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def execute_sql(db: Session, sql: str) -> ExecutionResult:
    """`db` must be a session bound to the readonly_engine — see app/db/session.py.

    Never call this with the privileged session; that would defeat the
    entire point of the read-only role.
    """
    try:
        result = db.execute(text(sql))
        columns = list(result.keys())
        rows = [
            {col: _json_safe(val) for col, val in zip(columns, row, strict=True)}
            for row in result.fetchall()
        ]
        return ExecutionResult(success=True, columns=columns, rows=rows, row_count=len(rows))
    except Exception as e:
        return ExecutionResult(success=False, columns=[], rows=[], row_count=0, error=str(e))
    finally:
        db.rollback()  # read-only session: never leave a transaction open
