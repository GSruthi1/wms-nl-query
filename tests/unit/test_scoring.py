from benchmark.scoring import compare_results


def test_identical_rows_match():
    rows = [{"sku": "A", "count": 3}, {"sku": "B", "count": 1}]
    assert compare_results(rows, rows).match


def test_different_row_order_still_matches():
    gold = [{"sku": "A", "count": 3}, {"sku": "B", "count": 1}]
    generated = [{"sku": "B", "count": 1}, {"sku": "A", "count": 3}]
    assert compare_results(gold, generated).match


def test_different_column_names_still_matches_on_values():
    gold = [{"sku": "A", "pick_count": 3}]
    generated = [{"item_sku": "A", "total": 3}]
    assert compare_results(gold, generated).match


def test_row_count_mismatch_fails():
    gold = [{"sku": "A"}, {"sku": "B"}]
    generated = [{"sku": "A"}]
    result = compare_results(gold, generated)
    assert not result.match
    assert "count mismatch" in result.reason.lower()


def test_different_values_fail():
    gold = [{"sku": "A", "count": 3}]
    generated = [{"sku": "A", "count": 5}]
    assert not compare_results(gold, generated).match


def test_empty_results_match_empty():
    assert compare_results([], []).match
