"""Create the wms_readonly Postgres role: SELECT-only on WMS data tables, no access to audit_log.

This is the DB-level enforcement layer described in app/db/session.py — the
only role the app ever uses to execute LLM-generated SQL. It deliberately
has no grant on audit_log, so a generated query can never read or tamper
with the audit trail even if the app-level validator has a bug.

The role's password comes from the READONLY_DB_PASSWORD env var so it isn't
hardcoded in version control; it falls back to a dev-only default matching
.env.example for local/CI use.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-26

"""
import os
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

READONLY_ROLE = "wms_readonly"
DATA_TABLES = ["locations", "items", "inventory", "picks", "receipts", "labor"]


def upgrade() -> None:
    password = os.environ.get("READONLY_DB_PASSWORD", "wms_readonly")

    # CREATE ROLE has no IF NOT EXISTS in Postgres, so guard with a DO block
    # — this migration must be safe to run against a DB where the role was
    # already created out-of-band (e.g. a managed Postgres that provisions
    # roles separately from migrations).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{READONLY_ROLE}') THEN
                CREATE ROLE {READONLY_ROLE} LOGIN PASSWORD '{password}';
            END IF;
        END
        $$;
        """
    )

    for table in DATA_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {READONLY_ROLE};")

    # No GRANT on audit_log — the omission is the point.


def downgrade() -> None:
    for table in DATA_TABLES:
        op.execute(f"REVOKE SELECT ON {table} FROM {READONLY_ROLE};")
    op.execute(f"DROP ROLE IF EXISTS {READONLY_ROLE};")
