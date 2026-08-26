"""
Safety validation for LLM-generated SQL, via sqlglot.

This is the app-level half of the defense-in-depth story (the other half is
the DB-level `wms_readonly` role grants in app/db/session.py). Nothing that
fails here reaches the database at all.
"""
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from app.core.config import get_settings

ALLOWED_TABLES = {"locations", "items", "inventory", "picks", "receipts", "labor"}
# Explicitly excluded even though it's a real table: the audit trail itself
# must never be readable or writable via generated SQL.
FORBIDDEN_TABLES = {"audit_log"}


@dataclass
class ValidationResult:
    passed: bool
    normalized_sql: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_and_normalize(sql: str) -> ValidationResult:
    if not sql or not sql.strip():
        return ValidationResult(passed=False, errors=["No SQL was generated."])

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception as e:  # sqlglot raises its own ParseError subclasses
        return ValidationResult(passed=False, errors=[f"SQL failed to parse: {e}"])

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return ValidationResult(
            passed=False,
            errors=[f"Expected exactly one statement, found {len(statements)}."],
        )

    stmt = statements[0]
    if not isinstance(stmt, exp.Select | exp.Union):
        return ValidationResult(
            passed=False,
            errors=[f"Only SELECT statements are allowed, got {type(stmt).__name__}."],
        )

    errors: list[str] = []
    warnings: list[str] = []

    tables = {t.name.lower() for t in stmt.find_all(exp.Table)}
    forbidden_hit = tables & FORBIDDEN_TABLES
    if forbidden_hit:
        errors.append(f"Query references restricted table(s): {sorted(forbidden_hit)}.")
    unknown_tables = tables - ALLOWED_TABLES - FORBIDDEN_TABLES
    if unknown_tables:
        errors.append(f"Query references unknown table(s): {sorted(unknown_tables)}.")

    # Belt-and-suspenders: reject if any DML/DDL node snuck in anywhere in
    # the tree (e.g. inside a CTE), even though the top-level type check
    # above should already prevent this.
    dml_node = stmt.find(exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter)
    if dml_node:
        errors.append(f"Query contains a disallowed {type(dml_node).__name__} operation.")

    if errors:
        return ValidationResult(passed=False, errors=errors)

    # Auto-inject a row cap if the query has none — a correct-but-unbounded
    # aggregate is unaffected (LIMIT on top of a small GROUP BY result is a
    # no-op); this exists to stop an accidentally huge unfiltered SELECT.
    settings = get_settings()
    if isinstance(stmt, exp.Select) and stmt.args.get("limit") is None:
        stmt = stmt.limit(settings.sql_row_limit)
        warnings.append(f"No LIMIT specified — capped at {settings.sql_row_limit} rows.")

    normalized = stmt.sql(dialect="postgres")
    return ValidationResult(passed=True, normalized_sql=normalized, warnings=warnings)
