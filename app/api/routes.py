from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db, get_readonly_db
from app.models.audit_log import AuditLog
from app.nl2sql.prompts import SCHEMA_DESCRIPTION, WMS_VOCABULARY
from app.schemas.audit import AuditLogEntry
from app.schemas.query import QueryRequest, QueryResponse
from app.services.query_service import run_query

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    db: Session = Depends(get_db),
    readonly_db: Session = Depends(get_readonly_db),
) -> QueryResponse:
    return run_query(request.question, db, readonly_db)


@router.get("/audit", response_model=list[AuditLogEntry])
def audit(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AuditLogEntry]:
    rows = db.execute(
        select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return [AuditLogEntry.model_validate(r) for r in rows]


@router.get("/schema")
def schema() -> dict:
    return {"schema_description": SCHEMA_DESCRIPTION, "wms_vocabulary": WMS_VOCABULARY}
