"""
Orchestrates one end-to-end query: generate -> validate -> confidence-score
-> execute -> explain -> audit-log.

This is the pipeline both the API (`POST /query`) and the benchmark runner
call — kept as one plain function (not tied to FastAPI) so both callers get
identical behavior and there's exactly one place this logic lives.
"""
import time
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.nl2sql.confidence import compute_confidence
from app.nl2sql.executor import execute_sql
from app.nl2sql.explainer import explain_results
from app.nl2sql.generator import generate_sql
from app.nl2sql.validator import validate_and_normalize
from app.schemas.query import QueryResponse


def run_query(question: str, db: Session, readonly_db: Session) -> QueryResponse:
    start = time.monotonic()

    generation = generate_sql(question)

    validation_passed = False
    validation_errors: list[str] = []
    validation_warnings: list[str] = []
    normalized_sql: str | None = None

    if not generation.answerable or not generation.sql:
        validation_errors = ["Model reported this question is not answerable from the schema."]
        confidence = round(min(generation.confidence, 0.15), 3)
    else:
        validation = validate_and_normalize(generation.sql)
        validation_passed = validation.passed
        validation_errors = validation.errors
        validation_warnings = validation.warnings
        normalized_sql = validation.normalized_sql
        confidence = compute_confidence(generation.confidence, validation)

    execution_success = False
    columns: list[str] = []
    rows: list[dict] = []
    row_count = 0
    exec_error: str | None = None
    explanation: str | None = None

    if validation_passed and normalized_sql:
        result = execute_sql(readonly_db, normalized_sql)
        execution_success = result.success
        columns = result.columns
        rows = result.rows
        row_count = result.row_count
        exec_error = result.error

        if execution_success:
            explanation = explain_results(question, normalized_sql, columns, rows, row_count)
        # An execution failure (e.g. a runtime type error) means the SQL
        # was syntactically/structurally valid but still wrong in a way
        # static validation can't catch — worth reflecting in confidence.
        else:
            confidence = round(min(confidence, 0.2), 3)
    elif not validation_passed:
        exec_error = "; ".join(validation_errors) if validation_errors else None

    latency_ms = int((time.monotonic() - start) * 1000)

    audit_row = AuditLog(
        ts=datetime.utcnow(),
        user_question=question,
        generated_sql=normalized_sql or generation.sql,
        confidence_score=confidence,
        validation_passed=validation_passed,
        execution_success=execution_success,
        row_count=row_count if execution_success else None,
        explanation=explanation,
        error_message=exec_error,
        latency_ms=latency_ms,
        llm_provider=generation.llm_provider,
    )
    db.add(audit_row)
    db.commit()

    return QueryResponse(
        question=question,
        answerable=generation.answerable,
        sql=normalized_sql or generation.sql,
        confidence=confidence,
        validation_passed=validation_passed,
        validation_errors=validation_errors,
        validation_warnings=validation_warnings,
        execution_success=execution_success,
        columns=columns,
        rows=rows,
        row_count=row_count,
        explanation=explanation,
        error=exec_error,
        latency_ms=latency_ms,
        llm_provider=generation.llm_provider,
    )
