# WMS Natural-Language Query Interface

A production-shaped portfolio project for WMS vendors (Manhattan Associates,
Blue Yonder, Körber, SAP EWM): an operations manager types a plain-English
question about warehouse operations, and the system converts it to SQL,
safety-validates it, runs it against live WMS data, and explains the result
in plain English — with every request audited.

## Results, up front

- **8/8 (100%)** on the seed benchmark (real Claude Sonnet 5 calls, no
  mocking) — up from 6/8 (75%) on the first run. The two misses weren't
  scoring artifacts: the model was adding unrequested extra columns and
  answering "which locations" at inventory-line granularity instead of
  distinct-location granularity. Both were fixed with explicit prompt rules
  and a few-shot example, not by loosening the scoring. See
  [`benchmark/questions.yaml`](benchmark/questions.yaml) and
  [Benchmark results](#benchmark-results) below.
- Correctly **refuses** questions the schema can't answer (e.g. cycle count
  — there's no cycle-count table) instead of hallucinating a plausible-
  looking but fake answer.
- Two independent safety layers block unsafe SQL before it ever touches
  data: an app-level `sqlglot` validator, and a Postgres role
  (`wms_readonly`) that can only `SELECT` from the six WMS data tables —
  not even `audit_log`. Verified directly against the DB grants, not just
  assumed from the code (see [Architecture](#architecture)).

## The problem this solves

Warehouse ops managers live in report builders and canned dashboards. A
question that isn't a pre-built report — "what are our hot picks this
month" or "which receipts blew dock-to-stock SLA last week" — means either
learning SQL or waiting on a BI request queue. This is a working NL→SQL
layer purpose-built for WMS vocabulary (hot picks, velocity class,
slotting, dock-to-stock, cycle count, put-away), not a generic
"talk-to-your-database" demo — it's tested against a real, skewed
synthetic cold-chain dataset (Pareto-distributed picks, a realistic
dock-to-stock long tail), not a toy table.

## Pipeline

1. Operations manager asks a question in the Streamlit UI.
2. **Generate**: an LLM call (Claude or GPT-4o, provider-swappable)
   converts the question to SQL using a system prompt that embeds the
   schema and WMS vocabulary translations, and self-reports a confidence
   score. If the question isn't answerable from the schema, it says so
   instead of guessing.
3. **Validate**: `sqlglot` parses the SQL and enforces: exactly one
   statement, `SELECT`-only (rejects DDL/DML even nested in a CTE), a
   table allowlist that explicitly excludes `audit_log`, and auto-injects
   a row-count `LIMIT` if the model omitted one.
4. **Score confidence**: the LLM's self-reported confidence is combined
   with the validation outcome — a validation failure hard-caps confidence
   low regardless of what the model claimed.
5. **Execute**: the (now-normalized) SQL runs against Postgres — but only
   over a connection authenticated as `wms_readonly`, a role with `SELECT`
   grants on the six data tables and nothing else.
6. **Explain**: a second LLM call summarizes the result set in plain
   English for a non-technical reader.
7. **Audit**: every request — question, SQL, confidence, validation and
   execution outcome, explanation, latency — is logged to `audit_log`,
   over a *separate, privileged* DB connection the read-only role can't
   touch.

## Architecture

The core design decision is **two Postgres roles, not one**:

```
                              ┌─────────────────────┐
   /query request  ────────▶ │   FastAPI (app/)     │
                              └──────────┬───────────┘
                                         │
                    generate → validate │ → execute → explain → log
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 │                                                │
        privileged connection                          wms_readonly connection
        (migrations, audit_log writes)                 (ONLY thing that runs
                 │                                       LLM-generated SQL)
                 ▼                                                ▼
        ALL tables, read/write                    SELECT-only, 6 data tables,
                                                    NO audit_log access,
                                                    session statement_timeout
```

This is deliberate defense-in-depth: the `sqlglot` validator is the
app-level check, but if it ever has a bug or gets bypassed, the DB-level
grant is what actually stops a write, a `DROP`, or a read of the audit
trail — because the role the SQL executes under is *incapable* of any of
that, independent of anything the app code decides. Verified directly:

```sql
SELECT table_name, privilege_type FROM information_schema.role_table_grants
WHERE grantee = 'wms_readonly' ORDER BY table_name;
-- inventory | SELECT
-- items     | SELECT
-- labor     | SELECT
-- locations | SELECT
-- picks     | SELECT
-- receipts  | SELECT
-- (audit_log correctly absent)
```

## Repo structure

```
app/
  core/       Settings (pydantic-settings), structlog config
  db/         Two SQLAlchemy engines: privileged + wms_readonly
  models/     locations, items, inventory, picks, receipts, labor, audit_log
  nl2sql/     prompts, generator, validator, confidence, executor, explainer
  api/        POST /query, GET /audit, GET /schema, GET /health
  services/   query_service.py — orchestrates the full pipeline
alembic/      0001 schema, 0002 wms_readonly role + grants
scripts/      generate_synthetic_data.py — realistic skewed Faker data
benchmark/    questions.yaml, scoring.py, run_benchmark.py
ui/           streamlit_app.py — thin HTTP client against the API
docker/       Dockerfile, entrypoint.sh (runs migrations on boot)
tests/        unit/ + integration/ (LLM calls mocked — no paid spend in CI)
```

## Running it locally

```bash
cp .env.example .env   # fill in ANTHROPIC_API_KEY (or OPENAI_API_KEY)
docker compose up -d --build
docker compose exec app python -m scripts.generate_synthetic_data
```

- API: http://localhost:8001 (`/health`, `/query`, `/audit`, `/schema`,
  interactive docs at `/docs`)
- UI: http://localhost:8501

(Ports are 8001/5433 rather than the more obvious 8000/5432 specifically so
this can run alongside another local Postgres-backed project without a
port collision — see the comments in `docker-compose.yml`.)

## API

`POST /query`
```json
{"question": "What are our top 5 hot picks this month?"}
```
returns the generated SQL, confidence score, validation outcome, result
rows, plain-English explanation, and latency.

`GET /audit?limit=50&offset=0` — paginated audit trail.

`GET /schema` — the schema description and WMS vocabulary glossary the
model is prompted with, exposed so the UI (or a curious caller) can show
what the system does and doesn't know about.

## Testing

```bash
docker compose exec -T db psql -U wms -d wms -c "CREATE DATABASE wms_test;"
DATABASE_URL=postgresql+psycopg2://wms:wms@localhost:5433/wms_test alembic upgrade head

DATABASE_URL_TEST=postgresql+psycopg2://wms:wms@localhost:5433/wms_test \
DATABASE_URL_READONLY=postgresql+psycopg2://wms_readonly:wms_readonly@localhost:5433/wms_test \
  pytest -m "not benchmark"
```

All LLM calls are mocked in the regular suite — CI never spends money on a
normal push/PR. The benchmark (`pytest -m benchmark`) makes real, paid
calls and only runs via manual `workflow_dispatch` in CI.

## Benchmark results

`benchmark/questions.yaml` holds hand-authored (question, gold SQL)
pairs — 8 seed questions here establishing the format across every
category (filter, join, aggregation, time-window, WMS jargon,
unanswerable); the target dataset is 50, written by someone with real
cold-chain WMS floor experience, not LLM-generated questions grading an
LLM's own guesses.

Scoring executes both the gold SQL and the generated SQL against the same
seeded database and diffs the **result sets** (column-name- and
column-order-insensitive), not the SQL text — two differently-written but
equally-correct queries both score as correct.

```
Overall accuracy: 100.0% (8/8) — target 88%
  filter          100.0%
  join            100.0%
  aggregation     100.0%
  time_window     100.0%
  jargon          100.0%
  unanswerable    100.0%
```

Reproduce with `docker compose exec app python -m benchmark.run_benchmark`.

## Deployment

`railway.json` + `docker/Dockerfile` are set up the same way as this
author's other deployed project (LDIP) — Dockerfile builder, `/health`
healthcheck, restart-on-failure. Deploy with:

```bash
railway up
railway domain --port 8000   # required — a Railway healthcheck fails
                              # silently without an explicit target port
```

## Key design decisions

- **Two DB roles, not app-level trust in the LLM's output.** Covered above
  under Architecture — this is the single most important design decision
  in the project and the one most worth defending in an interview.
- **Confidence is computed before execution, not after.** It reflects
  whether the *generation and validation* were trustworthy, matching the
  product's own step ordering (generate → confidence-score → execute). A
  query that's well-formed and safe but happens to error at runtime is
  tracked separately (`execution_success`), not folded backward into a
  confidence score that already shipped to the UI.
- **The model is allowed to say "I don't know."** `answerable=false` is a
  first-class outcome, not an error path — a schema-aware system that
  admits its limits is a stronger pitch to a WMS vendor than one that
  always produces *an* answer, correct or not.
- **Scoring compares results, not SQL text.** SQL-string matching would
  fail on any semantically-equivalent rewrite; result-set diffing is what
  actually answers "did this correctly answer the question."
