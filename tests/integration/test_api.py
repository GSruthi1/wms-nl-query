from fastapi.testclient import TestClient

from app.db.session import get_db, get_readonly_db
from app.main import app


def _override_get_db(session):
    def _get():
        yield session
    return _get


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_schema_endpoint():
    client = TestClient(app)
    resp = client.get("/schema")
    assert resp.status_code == 200
    assert "locations" in resp.json()["schema_description"]


def test_query_endpoint_mocked(monkeypatch, db_session, readonly_db_session):
    from app.nl2sql.generator import SQLGenerationResult

    monkeypatch.setattr(
        "app.services.query_service.generate_sql",
        lambda q: SQLGenerationResult(
            answerable=True, sql="SELECT 1 AS x", confidence=0.8,
            reasoning="t", llm_provider="anthropic",
        ),
    )
    monkeypatch.setattr(
        "app.services.query_service.explain_results", lambda *a, **k: "one row"
    )

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    app.dependency_overrides[get_readonly_db] = _override_get_db(readonly_db_session)
    try:
        client = TestClient(app)
        resp = client.post("/query", json={"question": "test?"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["execution_success"]
        assert body["explanation"] == "one row"

        audit_resp = client.get("/audit")
        assert audit_resp.status_code == 200
        assert len(audit_resp.json()) == 1
    finally:
        app.dependency_overrides.clear()
