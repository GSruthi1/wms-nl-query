"""
Wraps the benchmark eval as a pytest test. Makes real, paid LLM calls —
excluded from default `pytest` runs (see pytest.ini's `benchmark` marker
and .github/workflows/ci.yml, where it's workflow_dispatch-gated only).

Run explicitly with:
    pytest -m benchmark

Points at the real seeded dev database (DATABASE_URL_READONLY from .env),
not the disposable *_test database the rest of the suite uses — the
benchmark questions need actual synthetic data to score against.
"""
import pytest

from benchmark.run_benchmark import TARGET_ACCURACY, main


@pytest.mark.benchmark
def test_benchmark_meets_target_accuracy():
    report = main()
    summary = report["summary"]

    failures = [r for r in report["results"] if not r["match"]]
    detail = "\n".join(f"  [{r['category']}] {r['question']!r}: {r['reason']}" for r in failures)

    assert summary["overall_accuracy"] >= TARGET_ACCURACY, (
        f"Benchmark accuracy {summary['overall_accuracy']:.1%} is below the "
        f"{TARGET_ACCURACY:.0%} target.\nFailing questions:\n{detail}"
    )
