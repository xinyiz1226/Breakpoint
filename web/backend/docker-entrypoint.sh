#!/bin/sh
# Applies pending Alembic migrations then execs the production server.
# Kept as a tiny shell entrypoint (not baked into the Python app) so the
# API image never needs a migration flag/CLI branch in application code.
set -eu

alembic upgrade head
exec "$@"
