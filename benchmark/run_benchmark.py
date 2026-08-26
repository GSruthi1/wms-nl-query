"""
Runs the NL->SQL pipeline against benchmark/questions.yaml and scores it.

For each question: generates SQL, validates it, executes both the
generated SQL and the gold SQL against the same live (seeded) database, and
diffs the result sets (see scoring.py). Skips the explainer call and audit
logging — this is an eval run, not a served request, and skipping the
second LLM call halves the API cost of running the benchmark.

This makes real, paid LLM calls. Not run on every CI push — see
.github/workflows/ci.yml (workflow_dispatch only) and
tests/integration/test_benchmark.py (pytest -m benchmark).

Usage:
    python -m benchmark.run_benchmark
    python -m benchmark.run_benchmark --limit 3          # cheap smoke test
    python -m benchmark.run_benchmark --questions-file benchmark/questions.yaml
"""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.db.session import ReadOnlySessionLocal
from app.nl2sql.executor import execute_sql
from app.nl2sql.generator import generate_sql
from app.nl2sql.validator import validate_and_normalize
from benchmark.scoring import compare_results

DEFAULT_QUESTIONS_FILE = Path(__file__).parent / "questions.yaml"
DEFAULT_OUTPUT_FILE = Path(__file__).parent / "results" / "report.json"
TARGET_ACCURACY = 0.88


def load_questions(path: Path) -> list[dict]:
    with open(path) as f:
        return yaml.safe_load(f)


def run_one(question: dict, db) -> dict:
    generation = generate_sql(question["question"])
    expected_unanswerable = question["category"] == "unanswerable"

    record = {
        "id": question["id"],
        "question": question["question"],
        "category": question["category"],
        "difficulty": question["difficulty"],
        "expected_unanswerable": expected_unanswerable,
        "model_answerable": generation.answerable,
        "confidence": generation.confidence,
        "generated_sql": generation.sql,
        "validation_passed": None,
        "execution_success": None,
        "match": None,
        "reason": None,
    }

    if expected_unanswerable:
        # Correct behavior here is refusing, not producing SQL — scored
        # directly on the answerable flag, no execution involved.
        record["match"] = not generation.answerable
        record["reason"] = (
            "Correctly declined." if record["match"] else "Should have declined but generated SQL."
        )
        return record

    if not generation.answerable or not generation.sql:
        record["match"] = False
        record["reason"] = "Model declined an answerable question."
        return record

    validation = validate_and_normalize(generation.sql)
    record["validation_passed"] = validation.passed
    if not validation.passed:
        record["match"] = False
        record["reason"] = f"Failed safety validation: {validation.errors}"
        return record

    gen_result = execute_sql(db, validation.normalized_sql)
    gold_result = execute_sql(db, question["gold_sql"])

    record["execution_success"] = gen_result.success
    if not gold_result.success:
        record["match"] = False
        record["reason"] = f"Gold SQL itself failed to execute: {gold_result.error}"
        return record
    if not gen_result.success:
        record["match"] = False
        record["reason"] = f"Generated SQL failed to execute: {gen_result.error}"
        return record

    score = compare_results(gold_result.rows, gen_result.rows)
    record["match"] = score.match
    record["reason"] = score.reason
    return record


def summarize(records: list[dict]) -> dict:
    total = len(records)
    matched = sum(1 for r in records if r["match"])
    by_category: dict[str, dict] = {}
    for r in records:
        cat = by_category.setdefault(r["category"], {"total": 0, "matched": 0})
        cat["total"] += 1
        cat["matched"] += 1 if r["match"] else 0
    category_accuracy = {
        cat: round(v["matched"] / v["total"], 3) for cat, v in by_category.items()
    }

    matched_conf = [r["confidence"] for r in records if r["match"]]
    unmatched_conf = [r["confidence"] for r in records if not r["match"]]

    return {
        "total_questions": total,
        "overall_accuracy": round(matched / total, 3) if total else 0.0,
        "target_accuracy": TARGET_ACCURACY,
        "meets_target": (matched / total) >= TARGET_ACCURACY if total else False,
        "category_accuracy": category_accuracy,
        "avg_confidence_when_correct": round(sum(matched_conf) / len(matched_conf), 3)
        if matched_conf
        else None,
        "avg_confidence_when_incorrect": round(sum(unmatched_conf) / len(unmatched_conf), 3)
        if unmatched_conf
        else None,
    }


def main() -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions-file", type=Path, default=DEFAULT_QUESTIONS_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N questions.")
    args = parser.parse_args()

    questions = load_questions(args.questions_file)
    if args.limit:
        questions = questions[: args.limit]

    db = ReadOnlySessionLocal()
    try:
        records = [run_one(q, db) for q in questions]
    finally:
        db.close()

    summary = summarize(records)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "results": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n{'=' * 60}")
    print(f"Overall accuracy: {summary['overall_accuracy']:.1%} "
          f"({sum(1 for r in records if r['match'])}/{summary['total_questions']}) "
          f"— target {TARGET_ACCURACY:.0%}")
    for cat, acc in summary["category_accuracy"].items():
        print(f"  {cat:15s} {acc:.1%}")
    print(f"Report written to {args.output}")
    print(f"{'=' * 60}\n")

    return report


if __name__ == "__main__":
    main()
