"""Explicit accounting periods for quota ledger entries and reservations.

Adds:
- ``quota_ledger_entries.accounting_month`` (Date, first UTC day of month):
  the period a ledger entry counts against, independent of ``created_at``.
  A release or worker resize written after a calendar rollover for a
  reservation that belongs to an earlier month must carry that earlier
  month, not the month it happens to be written in, so monthly analysis usage
  never nets a stale-month event against the wrong month. Existing analysis
  rows are grouped by their asset/job lifecycle and inherit its first
  reservation month; unrelated rows fall back to their own ``created_at``
  month. The column is then made non-null and indexed on
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

from collections import defaultdict
from datetime import date
from typing import Any
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


def _backfill_analysis_lifecycle_months(bind: sa.engine.Connection) -> None:
    """Assign one accounting period to each recoverable analysis lifecycle."""
    job_by_id = {
        row.id: (row.video_asset_id, row.owner_id)
        for row in bind.execute(
            sa.text("SELECT id, video_asset_id, owner_id FROM analysis_jobs")
        )
    }
    asset_owner_by_id = {
        row.id: row.owner_id
        for row in bind.execute(sa.text("SELECT id, owner_id FROM video_assets"))
    }
    ownership_rows = bind.execute(
        sa.text(
            """
            SELECT id, user_id, analysis_job_id, video_asset_id
            FROM quota_ledger_entries
            WHERE analysis_job_id IS NOT NULL OR video_asset_id IS NOT NULL
            """
        )
    ).mappings().all()
    ownership_mismatches: list[tuple[Any, str]] = []
    for row in ownership_rows:
        asset_id = row["video_asset_id"]
        job_id = row["analysis_job_id"]
        if job_id is not None:
            job = job_by_id.get(job_id)
            if job is None:
                ownership_mismatches.append((row["id"], "missing analysis job"))
                continue
            job_asset_id, job_owner_id = job
            if row["user_id"] != job_owner_id:
                ownership_mismatches.append((row["id"], "analysis job owner"))
            if asset_id is not None and asset_id != job_asset_id:
                ownership_mismatches.append((row["id"], "analysis job asset"))
            if asset_id is None:
                asset_id = job_asset_id

        if asset_id is None:
            continue
        asset_owner_id = asset_owner_by_id.get(asset_id)
        if asset_owner_id is None:
            ownership_mismatches.append((row["id"], "missing video asset"))
        elif row["user_id"] != asset_owner_id:
            ownership_mismatches.append((row["id"], "video asset owner"))

    if ownership_mismatches:
        raise RuntimeError(
            "Cannot safely migrate quota ledger ownership mismatch: "
            f"{ownership_mismatches}"
        )

    rows = bind.execute(
        sa.text(
            """
            SELECT
                id,
                user_id,
                event_type,
                analysis_job_id,
                video_asset_id,
                seconds_delta,
                accounting_month,
                created_at
            FROM quota_ledger_entries
            WHERE event_type IN (
                'ANALYSIS_RESERVED',
                'ANALYSIS_RESERVATION_RELEASED',
                'ANALYSIS_COMPLETED'
            )
            ORDER BY created_at, id
            """
        )
    ).mappings().all()

    lifecycle_key_by_entry_id: dict[Any, tuple[Any, Any]] = {}
    lifecycle_month_by_key: dict[tuple[Any, Any], date | str] = {}
    reservation_balance_by_key: dict[tuple[Any, Any], float] = defaultdict(float)
    negative_lifecycles: list[tuple[tuple[Any, Any], Any, float]] = []
    for row in rows:
        asset_id = row["video_asset_id"]
        job_id = row["analysis_job_id"]
        if job_id is not None:
            job = job_by_id[job_id]
            job_asset_id, _job_owner_id = job
            if asset_id is None:
                asset_id = job_asset_id
        if asset_id is None:
            continue

        lifecycle_key = (asset_id, row["user_id"])
        lifecycle_key_by_entry_id[row["id"]] = lifecycle_key
        if row["event_type"] in (
            "ANALYSIS_RESERVED",
            "ANALYSIS_RESERVATION_RELEASED",
        ):
            reservation_balance_by_key[lifecycle_key] += float(
                row["seconds_delta"] or 0.0
            )
            if reservation_balance_by_key[lifecycle_key] < -1e-9:
                negative_lifecycles.append(
                    (
                        lifecycle_key,
                        row["id"],
                        reservation_balance_by_key[lifecycle_key],
                    )
                )
        if row["event_type"] == "ANALYSIS_RESERVED" and row["seconds_delta"] is not None:
            existing = lifecycle_month_by_key.get(lifecycle_key)
            if existing is None or row["accounting_month"] < existing:
                lifecycle_month_by_key[lifecycle_key] = row["accounting_month"]

    if negative_lifecycles:
        raise RuntimeError(
            "Cannot safely migrate negative analysis reservation lifecycles: "
            f"{negative_lifecycles}"
        )

    entry_updates = [
        {
            "id": row["id"],
            "accounting_month": lifecycle_month_by_key[lifecycle_key_by_entry_id[row["id"]]],
        }
        for row in rows
        if row["id"] in lifecycle_key_by_entry_id
        and lifecycle_key_by_entry_id[row["id"]] in lifecycle_month_by_key
    ]
    if entry_updates:
        bind.execute(
            sa.text(
                """
                UPDATE quota_ledger_entries
                SET accounting_month = :accounting_month
                WHERE id = :id
                """
            ),
            entry_updates,
        )

    live_asset_updates = [
        {"id": asset_id, "accounting_month": accounting_month}
        for (asset_id, _user_id), accounting_month in lifecycle_month_by_key.items()
    ]
    if live_asset_updates:
        bind.execute(
            sa.text(
                """
                UPDATE video_assets
                SET analysis_reservation_month = :accounting_month
                WHERE id = :id AND analysis_reserved_seconds > 0
                """
            ),
            live_asset_updates,
        )

    _normalize_unassociated_negative_analysis_periods(
        bind,
        associated_entry_ids=set(lifecycle_key_by_entry_id),
    )


def _normalize_unassociated_negative_analysis_periods(
    bind: sa.engine.Connection,
    *,
    associated_entry_ids: set[Any],
) -> None:
    """Move recoverable orphan releases to an earlier positive period.

    Rows without an asset/job association retain their created-at month unless
    that would create a negative monthly balance. In that case, an orphan
    release can safely consume a prior positive balance for the same user.
    Irrecoverably malformed history aborts the migration instead of granting
    quota through a negative balance.
    """
    rows = bind.execute(
        sa.text(
            """
            SELECT
                id,
                user_id,
                event_type,
                seconds_delta,
                accounting_month,
                created_at
            FROM quota_ledger_entries
            WHERE event_type IN (
                'ANALYSIS_RESERVED',
                'ANALYSIS_RESERVATION_RELEASED'
            )
            ORDER BY created_at, id
            """
        )
    ).mappings().all()

    balance_by_user_month: dict[tuple[Any, date | str], float] = defaultdict(float)
    for row in rows:
        if row["id"] in associated_entry_ids:
            continue
        balance_by_user_month[(row["user_id"], row["accounting_month"])] += float(
            row["seconds_delta"] or 0.0
        )

    orphan_releases = [
        row
        for row in rows
        if row["id"] not in associated_entry_ids
        and row["event_type"] == "ANALYSIS_RESERVATION_RELEASED"
        and float(row["seconds_delta"] or 0.0) < 0
    ]
    updates: list[dict[str, Any]] = []
    for row in orphan_releases:
        user_id = row["user_id"]
        current_month = row["accounting_month"]
        current_key = (user_id, current_month)
        if balance_by_user_month[current_key] >= 0:
            continue

        release_amount = -float(row["seconds_delta"])
        candidate_months = sorted(
            (
                month
                for (candidate_user_id, month), balance in balance_by_user_month.items()
                if candidate_user_id == user_id
                and month < current_month
                and balance >= release_amount
            ),
            reverse=True,
        )
        if not candidate_months:
            continue

        original_month = candidate_months[0]
        balance_by_user_month[current_key] += release_amount
        balance_by_user_month[(user_id, original_month)] -= release_amount
        updates.append({"id": row["id"], "accounting_month": original_month})

    if updates:
        bind.execute(
            sa.text(
                """
                UPDATE quota_ledger_entries
                SET accounting_month = :accounting_month
                WHERE id = :id
                """
            ),
            updates,
        )

    negative_balances = [
        (user_id, month, balance)
        for (user_id, month), balance in balance_by_user_month.items()
        if balance < -1e-9
    ]
    if negative_balances:
        raise RuntimeError(
            "Cannot safely migrate negative monthly analysis quota balances: "
            f"{negative_balances}"
        )


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

    # Reservation releases and worker resizes are compensating entries in the
    # original reservation lifecycle, not new accounting-period activity.
    # Resolve rows through either video_asset_id or analysis_job_id and assign
    # the earliest reservation month to the full lifecycle.
    _backfill_analysis_lifecycle_months(bind)

    # Storage is a standing all-history occupancy balance rather than a
    # monthly allowance. Its durable live-reservation period is retained for
    # audit, using the matching reservation row when available.
    month_from_asset_created_at = _month_start_expression(
        "video_assets.created_at", bind.dialect.name
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
    bind.execute(
        sa.text(
            f"""
            UPDATE video_assets
            SET analysis_reservation_month = {month_from_asset_created_at}
            WHERE analysis_reserved_seconds > 0
              AND analysis_reservation_month IS NULL
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
