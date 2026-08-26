"""query_service tests with the LLM calls mocked — no real API spend."""
from app.models.item import Item
from app.nl2sql.generator import SQLGenerationResult
from app.services.query_service import run_query


def _fake_generation(sql: str, confidence: float = 0.9, answerable: bool = True):
    return SQLGenerationResult(
        answerable=answerable, sql=sql, confidence=confidence,
        reasoning="test", llm_provider="anthropic",
    )


def test_run_query_happy_path(monkeypatch, db_session, readonly_db_session):
    db_session.add(Item(
        sku="SKU-TEST01", description="Test Item", velocity_class="A",
        temperature_class="frozen", uom="EA", case_pack=1,
    ))
    db_session.commit()

    monkeypatch.setattr(
        "app.services.query_service.generate_sql",
        # Explicit LIMIT so this stays a clean "no warnings" happy path —
        # the no-LIMIT case (which knocks confidence down) is covered by
        # test_validator.py and test_confidence.py instead.
        lambda q: _fake_generation("SELECT sku FROM items LIMIT 10"),
    )
    monkeypatch.setattr(
        "app.services.query_service.explain_results",
        lambda *a, **k: "There is one test item.",
    )

    response = run_query("how many items?", db_session, readonly_db_session)

    assert response.validation_passed
    assert response.execution_success
    assert response.row_count == 1
    assert response.explanation == "There is one test item."
    assert response.confidence == 0.9


def test_run_query_writes_audit_row(monkeypatch, db_session, readonly_db_session):
    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    monkeypatch.setattr(
        "app.services.query_service.generate_sql",
        lambda q: _fake_generation("SELECT 1 AS x"),
    )
    monkeypatch.setattr(
        "app.services.query_service.explain_results", lambda *a, **k: "explanation"
    )

    run_query("a test question", db_session, readonly_db_session)

    rows = db_session.execute(select(AuditLog)).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_question == "a test question"
    assert rows[0].execution_success


def test_run_query_unanswerable_skips_execution(monkeypatch, db_session, readonly_db_session):
    monkeypatch.setattr(
        "app.services.query_service.generate_sql",
        lambda q: _fake_generation(None, confidence=0.9, answerable=False),
    )

    response = run_query("something out of scope", db_session, readonly_db_session)

    assert not response.answerable
    assert not response.validation_passed
    assert not response.execution_success
    assert response.confidence <= 0.15


def test_run_query_blocks_unsafe_sql(monkeypatch, db_session, readonly_db_session):
    monkeypatch.setattr(
        "app.services.query_service.generate_sql",
        lambda q: _fake_generation("DROP TABLE items"),
    )

    response = run_query("do something bad", db_session, readonly_db_session)

    assert not response.validation_passed
    assert not response.execution_success
    assert response.confidence <= 0.15
