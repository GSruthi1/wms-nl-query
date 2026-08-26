import pytest

from app.nl2sql.validator import validate_and_normalize


def test_valid_select_passes():
    result = validate_and_normalize("SELECT sku FROM items WHERE velocity_class = 'A'")
    assert result.passed
    assert "LIMIT" in result.normalized_sql.upper()  # auto-injected
    assert result.warnings


def test_valid_select_with_limit_keeps_it_unmodified():
    result = validate_and_normalize("SELECT sku FROM items LIMIT 10")
    assert result.passed
    assert not result.warnings


def test_empty_sql_fails():
    result = validate_and_normalize("")
    assert not result.passed


def test_drop_table_is_rejected():
    result = validate_and_normalize("DROP TABLE items")
    assert not result.passed


def test_multi_statement_is_rejected():
    result = validate_and_normalize("SELECT 1; DROP TABLE items;")
    assert not result.passed


def test_audit_log_table_is_rejected():
    result = validate_and_normalize("SELECT * FROM audit_log")
    assert not result.passed
    assert any("audit_log" in e for e in result.errors)


def test_unknown_table_is_rejected():
    result = validate_and_normalize("SELECT * FROM users")
    assert not result.passed


def test_insert_disguised_in_cte_is_rejected():
    result = validate_and_normalize(
        "WITH x AS (SELECT 1) INSERT INTO items (sku) SELECT 'x' FROM x"
    )
    assert not result.passed


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM picks",
        "SELECT i.sku FROM items i JOIN inventory inv ON i.sku = inv.sku",
    ],
)
def test_various_valid_selects_pass(sql):
    assert validate_and_normalize(sql).passed
