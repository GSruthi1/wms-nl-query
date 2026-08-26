"""LLM call #2: query results -> plain-English explanation for an ops manager."""
import json

from app.nl2sql.llm_client import generate_structured
from app.nl2sql.prompts import EXPLAIN_SYSTEM_PROMPT

EXPLAIN_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "explanation": {
            "type": "string",
            "description": "Plain-English explanation of the results, max 3-4 sentences.",
        },
    },
    "required": ["explanation"],
}

# Results are truncated before being shown to the LLM — an ops manager's
# question doesn't need 500 raw rows echoed back to summarize, and it keeps
# the explanation call cheap regardless of SQL_ROW_LIMIT.
MAX_ROWS_IN_PROMPT = 20


def explain_results(question: str, sql: str, columns: list[str], rows: list[dict], row_count: int) -> str:
    if row_count == 0:
        preview = "(no rows returned)"
    else:
        preview = json.dumps(rows[:MAX_ROWS_IN_PROMPT], default=str)

    user_prompt = (
        f"Original question: {question}\n"
        f"SQL executed: {sql}\n"
        f"Total rows returned: {row_count}\n"
        f"Columns: {columns}\n"
        f"Result preview (first {min(row_count, MAX_ROWS_IN_PROMPT)} rows): {preview}"
    )
    raw = generate_structured(
        system_prompt=EXPLAIN_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tool_name="emit_explanation",
        tool_description="Emit the plain-English explanation of these results.",
        input_schema=EXPLAIN_TOOL_SCHEMA,
    )
    return raw.get("explanation", "")
