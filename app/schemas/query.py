from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    question: str
    answerable: bool
    sql: str | None
    confidence: float
    validation_passed: bool
    validation_errors: list[str] = []
    validation_warnings: list[str] = []
    execution_success: bool
    columns: list[str] = []
    rows: list[dict] = []
    row_count: int
    explanation: str | None
    error: str | None = None
    latency_ms: int
    llm_provider: str
