"""quota override non-negative check constraints

NULL means "use the configured default" for both per-user quota override
columns; 0 is a valid override meaning "no quota" and must not be treated
the same as NULL (see app.services.quota, which selects overrides via
`is not None` rather than truthiness). Negative values are nonsensical for
either limit, so this adds a DB-level CHECK constraint alongside the
application-level distinction.

Uses batch mode so this applies portably: a direct ALTER TABLE ADD
CONSTRAINT on Postgres, and Alembic's automatic table-recreate strategy on
SQLite (which has no ALTER TABLE ADD CONSTRAINT support at all).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-28 11:45:52.921433

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.create_check_constraint(
            "ck_users_quota_monthly_analysis_seconds_override_non_negative",
            "quota_monthly_analysis_seconds_override IS NULL OR quota_monthly_analysis_seconds_override >= 0",
        )
        batch_op.create_check_constraint(
            "ck_users_quota_max_active_analysis_jobs_override_non_negative",
            "quota_max_active_analysis_jobs_override IS NULL OR quota_max_active_analysis_jobs_override >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint(
            "ck_users_quota_max_active_analysis_jobs_override_non_negative", type_="check"
        )
        batch_op.drop_constraint(
            "ck_users_quota_monthly_analysis_seconds_override_non_negative", type_="check"
        )
