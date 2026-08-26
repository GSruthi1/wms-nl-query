"""
Result-set comparison for benchmark scoring.

Deliberately NOT string-comparing SQL: two different-but-equally-correct
SQL formulations (different join order, different alias names, `count(*)`
vs `count(1)`) should both score as correct. What actually matters is
whether the generated query returns the same answer as the gold query.

Row comparison is column-order- and column-name-insensitive (each row is
reduced to a sorted tuple of its stringified values) but IS
duplicate-sensitive and count-sensitive — two rows with the same values in
different columns would still incorrectly match, but that's a rare
coincidence for the kinds of aggregate/filter results benchmark questions
return, and it's a deliberate simplicity/robustness tradeoff over building
a full column-alignment solver.
"""
from collections import Counter
from dataclasses import dataclass


@dataclass
class ScoreResult:
    match: bool
    reason: str


def _row_signature(row: dict) -> tuple:
    return tuple(sorted(str(v) for v in row.values()))


def _multiset(rows: list[dict]) -> Counter:
    return Counter(_row_signature(row) for row in rows)


def compare_results(gold_rows: list[dict], generated_rows: list[dict]) -> ScoreResult:
    if len(gold_rows) != len(generated_rows):
        return ScoreResult(
            match=False,
            reason=f"Row count mismatch: gold={len(gold_rows)}, generated={len(generated_rows)}.",
        )
    if _multiset(gold_rows) == _multiset(generated_rows):
        return ScoreResult(match=True, reason="Row content matches (order/column-name independent).")
    return ScoreResult(match=False, reason="Same row count but different row content.")
