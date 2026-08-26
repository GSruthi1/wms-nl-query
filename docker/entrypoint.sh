#!/bin/sh
set -e

# Run migrations before the app starts serving traffic. Safe to run on
# every boot — Alembic no-ops if already at head.
alembic upgrade head

exec "$@"
