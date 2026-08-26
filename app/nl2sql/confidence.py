"""
Composite confidence score.

Deliberately not just "whatever the LLM said" — an LLM can be confidently
wrong. Validation failure hard-caps the score low regardless of the LLM's
self-report; each soft warning (e.g. "had to auto-add a LIMIT") shaves a
bit more off. This runs BEFORE execution (matches the product's step
ordering: generate -> confidence-score -> execute), so it reflects
generation+validation quality, not whether the query happened to run.
"""
from app.nl2sql.validator import ValidationResult

VALIDATION_FAILURE_CAP = 0.15
WARNING_PENALTY = 0.1


def compute_confidence(llm_confidence: float, validation: ValidationResult) -> float:
    llm_confidence = max(0.0, min(1.0, llm_confidence))

    if not validation.passed:
        return round(min(llm_confidence, VALIDATION_FAILURE_CAP), 3)

    penalty = WARNING_PENALTY * len(validation.warnings)
    return round(max(0.0, min(1.0, llm_confidence - penalty)), 3)
