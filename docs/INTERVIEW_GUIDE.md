# How to talk about this project

## The 30-second pitch

"I built a natural-language query interface for WMS data — an ops manager
types 'what are our hot picks this month' and gets back safety-validated
SQL, the actual results, and a plain-English explanation. The part I'd
lead with in an interview isn't the LLM call, it's the safety layer: the
generated SQL runs under a dedicated Postgres role that can only `SELECT`
from the six operational tables — it can't write anything, and it can't
even read the audit log of its own past queries. That's enforced at the
database level, not just trusted from application code. And when a
question falls outside the schema — I tested this with a cycle-count
question, since this schema has no cycle-count table — it says so instead
of making something up."

## The problem, in one sentence

Ops managers have questions that don't map to a pre-built report, and the
alternative to a NL→SQL layer is "learn SQL" or "file a BI ticket."

## The pipeline, as an analogy

Think of it like a translator working in a courtroom who isn't allowed to
touch the evidence, only describe it: the LLM (translator) converts the
question into SQL, but the SQL it produces goes through a checkpoint
(`sqlglot` validator) before it's allowed anywhere near the database, and
even past that checkpoint, it can only ever *read* — never write, never
see anything outside the six rooms (tables) it's allowed into.

## Why two database roles, not one

This is the answer to "how do you know the LLM won't do something
destructive." The honest answer is layered, not "we trust the prompt":

1. The system prompt instructs SELECT-only, with few-shot examples.
2. `app/nl2sql/validator.py` parses the SQL with `sqlglot` and rejects
   anything that isn't a single `SELECT`/`WITH...SELECT` statement,
   rejects any DDL/DML node found anywhere in the parse tree (even nested
   in a CTE), and rejects a fixed table allowlist that explicitly excludes
   `audit_log`.
3. Even if both of those had a bug, the SQL executes under `wms_readonly`
   — a Postgres role created in `alembic/versions/0002_readonly_role.py`
   with `GRANT SELECT` on the six data tables and nothing else. A `DROP
   TABLE` or a `SELECT * FROM audit_log` fails with a Postgres permission
   error no matter what the app code does, because the role itself is
   incapable of it.

Layer 3 is the one that actually matters under "what if your code has a
bug" — it's the only layer that doesn't depend on the app being correct.

## The benchmark, and how to talk about the numbers

The honest framing: **8 seed questions, 100% on the second run, 75% on the
first.** That gap is more interesting than the final number. The first run
surfaced two real gaps, not scoring bugs:

- A "which items are chilled" question got answered correctly in content
  but with extra unrequested columns (`velocity_class`, `uom`,
  `case_pack`) — same rows, wrong shape, so it correctly scored as a miss
  under result-set comparison.
- A "which locations hold X" question got answered at inventory-line
  granularity (74 rows) instead of distinct-location granularity (27
  rows) — a real interpretation gap between "which locations" and "which
  inventory records."

Both were fixed with two explicit prompt rules (don't add unrequested
columns; "which X" means distinct X unless line-level detail is asked
for) and one new few-shot example — not by loosening what counts as a
correct answer. If asked "why only 8 questions, not the full 50" — the
target 50 are meant to be written by someone with real WMS floor
experience, and synthetic LLM-generated benchmark questions mostly just
test whether a model can guess its own training-data patterns, not real
domain competence.

## "Tell me about a bug you debugged"

The Streamlit `ui` service crash-looped on first boot: the container ran
`docker/entrypoint.sh`, which runs `alembic upgrade head` before starting
anything — a step that made sense for the API container but not for a
UI-only container with no `DATABASE_URL` configured at all, so it failed
trying to connect to a Postgres that, from its point of view, didn't
exist. Fixed by overriding `entrypoint: []` for the `ui` service in
`docker-compose.yml` so it skips straight to the `streamlit run` command —
migrations stay owned by exactly one service (`app`), which is also just
the more correct design (nothing about a UI container should be able to
touch schema state).

A second one, smaller: the same image forgot to `COPY ui ./ui` in the
Dockerfile in the first place — an easy one to hit when a service gets
added to `docker-compose.yml` before the Dockerfile catches up, and a good
reminder to actually run every service, not just the one you were
focused on.

## Anticipated questions and how to answer them

**"Why not just give the LLM raw database credentials?"** Because then the
only thing standing between a bad or adversarial prompt and a `DROP TABLE`
is prompt-following behavior — which is exactly the layer known to be
occasionally wrong. The read-only role turns "the LLM behaved" from a
requirement into a nice-to-have.

**"How do you know the confidence score means anything?"** It's not
purely the LLM's self-report — a validation failure hard-caps it low
regardless of what the model claimed, and the benchmark report tracks
`avg_confidence_when_correct` vs `avg_confidence_when_incorrect` as a
calibration check, not just an accuracy number.

**"What happens if the LLM writes a slow query?"** The `wms_readonly`
connection sets a session-level `statement_timeout` (5s default,
configurable) on every connection — a runaway query gets killed by
Postgres itself, not by an app-level timeout that might not fire.

**"Why Claude/GPT-4o and not a smaller/local model?"** The provider is a
config flag (`LLM_PROVIDER`), not a hardcoded dependency — both
`nl2sql/llm_client.py`'s Anthropic and OpenAI paths go through structured
tool-calling rather than "please output JSON" prompting, specifically
because that's what makes the `sql`/`confidence`/`answerable` fields
reliably parseable instead of occasionally wrapped in prose.

## If asked to whiteboard it

Draw the two-role split first — privileged connection on one side (writes
`audit_log`, runs migrations), `wms_readonly` connection on the other
(the only thing that ever runs LLM-generated SQL), and make the point
that `audit_log` sits only on the privileged side, so a generated query
structurally cannot read its own audit trail. Then draw the
generate → validate → confidence → execute → explain → log pipeline as a
straight line through the top, with the validator as a gate the SQL has
to pass before it's allowed to reach the `wms_readonly` box at all.
