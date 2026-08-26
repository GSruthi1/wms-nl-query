from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: datetime
    user_question: str
    generated_sql: str | None
    confidence_score: float | None
    validation_passed: bool
    execution_success: bool
    row_count: int | None
    explanation: str | None
    error_message: str | None
    latency_ms: int | None
    llm_provider: str | None
