from app.nl2sql.confidence import compute_confidence
from app.nl2sql.validator import ValidationResult


def test_passed_validation_no_warnings_keeps_llm_confidence():
    v = ValidationResult(passed=True, normalized_sql="SELECT 1", warnings=[])
    assert compute_confidence(0.9, v) == 0.9


def test_failed_validation_hard_caps_confidence():
    v = ValidationResult(passed=False, errors=["bad"])
    assert compute_confidence(0.95, v) <= 0.15


def test_warnings_reduce_confidence():
    v = ValidationResult(passed=True, normalized_sql="SELECT 1", warnings=["no limit"])
    assert compute_confidence(0.9, v) < 0.9


def test_confidence_is_clamped_to_0_1():
    v = ValidationResult(passed=True, normalized_sql="SELECT 1", warnings=[])
    assert compute_confidence(1.5, v) == 1.0
    assert compute_confidence(-0.5, v) == 0.0
