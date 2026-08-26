from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """One row per /query request — the full trail: question in, SQL out, what happened.

    Written over the privileged DB connection (never the read-only one that
    executes generated SQL), and is itself excluded from the read-only
    role's grants so a generated query can never read or tamper with its
    own audit trail.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    user_question: Mapped[str] = mapped_column(Text)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_success: Mapped[bool] = mapped_column(Boolean, default=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
