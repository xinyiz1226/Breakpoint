"""Explicit accounting periods for quota ledger entries and reservations.

Adds:
- ``quota_ledger_entries.accounting_month`` (Date, first UTC day of month):
  the period a ledger entry counts against, independent of ``created_at``.
  A release or worker resize written after a calendar rollover for a
  reservation that belongs to an earlier month must carry that earlier
  month, not the month it happens to be written in, so monthly analysis
  usage never nets a stale-month event against the wrong month. Backfilled
  from each existing row's ``created_at`` (truncated to its UTC calendar
  month) before being made non-null, then indexed on
  ``(user_id, accounting_month)``.
- ``video_assets.analysis_reservation_month`` / ``storage_reservation_month``
  (Date, nullable): durable memory of which accounting period a *live*
  reservation belongs to, set when the reservation is created/resized and
  cleared when released. Existing live reservations are backfilled from
  their latest matching reservation ledger row. The asset creation month is
  the conservative fallback if a legacy live reservation has no matching
  ledger row, preventing a later release from debiting the deployment month.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _month_start_expression(column_name: str, dialect_name: str) -> str:
    if dialect_name == "postgresql":
        # date_trunc(timestamptz) otherwise uses the session TimeZone, which
        # can assign UTC boundary rows to the wrong accounting month.
        return f"date_trunc('month', {column_name} AT TIME ZONE 'UTC')::date"
    return f"date({column_name}, 'start of month')"


def upgrade() -> None:
    op.add_column("quota_ledger_entries", sa.Column("accounting_month", sa.Date(), nullable=True))
    op.add_column("video_assets", sa.Column("analysis_reservation_month", sa.Date(), nullable=True))
    op.add_column("video_assets", sa.Column("storage_reservation_month", sa.Date(), nullable=True))

    bind = op.get_bind()

    # Backfill every existing row's accounting_month from its own
    # created_at, truncated to the first day of its UTC calendar month.
    # date(created_at, 'start of month') is portable SQLite date-function
    # syntax; Postgres uses date_trunc. Dispatch on dialect since there is
    # no single portable expression for calendar-month truncation.
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                f"""
                UPDATE quota_ledger_entries
                SET accounting_month = {_month_start_expression("created_at", bind.dialect.name)}
                """
            )
        )
    else:
        bind.execute(
            sa.text(
                """
                UPDATE quota_ledger_entries
                SET accounting_month = date(created_at, 'start of month')
                """
            )
        )

    # Preserve the accounting period for reservations that are still live at
    # deploy time. The latest reservation event is authoritative after a
    # worker resize; asset.created_at is a safe fallback for malformed legacy
    # rows because initiation creates both the asset and its first reservation
    # together.
    month_from_asset_created_at = _month_start_expression(
        "video_assets.created_at", bind.dialect.name
    )

    bind.execute(
        sa.text(
            f"""
            UPDATE video_assets
            SET analysis_reservation_month = COALESCE(
                (
                    SELECT quota_ledger_entries.accounting_month
                    FROM quota_ledger_entries
                    WHERE quota_ledger_entries.video_asset_id = video_assets.id
                      AND quota_ledger_entries.event_type = 'ANALYSIS_RESERVED'
                    ORDER BY quota_ledger_entries.created_at DESC, quota_ledger_entries.id DESC
                    LIMIT 1
                ),
                {month_from_asset_created_at}
            )
            WHERE analysis_reserved_seconds > 0
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            UPDATE video_assets
            SET storage_reservation_month = COALESCE(
                (
                    SELECT quota_ledger_entries.accounting_month
                    FROM quota_ledger_entries
                    WHERE quota_ledger_entries.video_asset_id = video_assets.id
                      AND quota_ledger_entries.event_type = 'STORAGE_RESERVED'
                    ORDER BY quota_ledger_entries.created_at DESC, quota_ledger_entries.id DESC
                    LIMIT 1
                ),
                {month_from_asset_created_at}
            )
            WHERE storage_reserved_bytes > 0
            """
        )
    )

    with op.batch_alter_table("quota_ledger_entries") as batch_op:
        batch_op.alter_column("accounting_month", existing_type=sa.Date(), nullable=False)

    op.create_index(
        op.f("ix_quota_ledger_entries_user_id_accounting_month"),
        "quota_ledger_entries",
        ["user_id", "accounting_month"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_quota_ledger_entries_user_id_accounting_month"),
        table_name="quota_ledger_entries",
    )
    with op.batch_alter_table("quota_ledger_entries") as batch_op:
        batch_op.alter_column("accounting_month", existing_type=sa.Date(), nullable=True)
    op.drop_column("quota_ledger_entries", "accounting_month")
    op.drop_column("video_assets", "storage_reservation_month")
    op.drop_column("video_assets", "analysis_reservation_month")
