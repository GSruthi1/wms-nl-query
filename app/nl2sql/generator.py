"""LLM call #1: natural-language question -> candidate SQL + self-reported confidence."""
from pydantic import BaseModel

from app.core.config import get_settings
from app.nl2sql.llm_client import generate_structured
from app.nl2sql.prompts import SYSTEM_PROMPT

GENERATE_SQL_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {
            "type": "boolean",
            "description": "Whether this question can be answered from the given schema.",
        },
        "sql": {
            "type": ["string", "null"],
            "description": "A single read-only SELECT statement, or null if not answerable.",
        },
        "confidence": {
            "type": "number",
            "description": "0.0-1.0 self-assessed confidence the SQL correctly and completely answers the question.",
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of the approach, or why the question isn't answerable.",
        },
    },
    "required": ["answerable", "sql", "confidence", "reasoning"],
}


class SQLGenerationResult(BaseModel):
    answerable: bool
    sql: str | None
    confidence: float
    reasoning: str
    llm_provider: str


def generate_sql(question: str) -> SQLGenerationResult:
    settings = get_settings()
    raw = generate_structured(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=question,
        tool_name="emit_sql",
        tool_description="Emit the generated SQL (or explain why the question isn't answerable).",
        input_schema=GENERATE_SQL_TOOL_SCHEMA,
    )
    return SQLGenerationResult(
        answerable=bool(raw.get("answerable", False)),
        sql=raw.get("sql"),
        confidence=float(raw.get("confidence", 0.0)),
        reasoning=raw.get("reasoning", ""),
        llm_provider=settings.llm_provider,
    )
