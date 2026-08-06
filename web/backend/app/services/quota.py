"""Quota accounting: limits, usage aggregation, and ledger writes.

This module only computes numbers and appends ledger rows; it deliberately
does not raise HTTP errors so it stays reusable from any call site (routers
decide what to do with the numbers).

Monthly analysis-seconds usage is bucketed by ``QuotaLedgerEntry.
accounting_month`` -- the reservation's own period -- not by ``created_at``.
A reservation created in one month and released (or resized by the worker)
after the calendar rolls over to the next month carries the *original*
month forward on that release/resize entry, so it nets correctly against
the month it actually belongs to instead of retroactively (and incorrectly)
affecting the month the release/resize happened to run in.

Storage-byte usage (``storage_bytes_used``) is intentionally not bucketed
by month at all: it represents current reserved+stored occupancy against a
standing limit, not a monthly allowance, so it sums the full ledger history
regardless of ``accounting_month``. It still records ``accounting_month``
on every entry for audit, and remains a safe running balance across
rollover because release/delete events are idempotent (see
app.services.reservations) rather than because of any month-scoped filter.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.enums import ACTIVE_JOB_STATUSES, QuotaLedgerEventType
from app.models.job import AnalysisJob
from app.models.quota import QuotaLedgerEntry, current_accounting_month
from app.models.user import User


def monthly_analysis_seconds_limit(user: User, settings: Settings) -> int:
    override = user.quota_monthly_analysis_seconds_override
    return override if override is not None else settings.default_monthly_analysis_seconds


def storage_bytes_limit(user: User, settings: Settings) -> int:
    override = user.quota_storage_bytes_override
    return override if override is not None else settings.default_storage_bytes


def max_active_analysis_jobs(user: User, settings: Settings) -> int:
    override = user.quota_max_active_analysis_jobs_override
    return override if override is not None else settings.default_max_active_analysis_jobs


def _current_month_start(now: datetime | None = None) -> datetime:
    reference = now or datetime.now(timezone.utc)
    return reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def monthly_analysis_seconds_used(
    db: Session,
    user_id: uuid.UUID,
    *,
    now: datetime | None = None,
    accounting_month: date | None = None,
) -> float:
    """Sum of seconds currently counted against the caller's monthly quota
    for a given accounting period (default: the current UTC month).

    This is a running ledger balance, not just completed usage: it nets
    provisional reservations against their releases so a reservation that
    was never followed by an ``ANALYSIS_COMPLETED`` (e.g. an aborted
    finalize, or a future worker rejecting an over-limit asset) stops
    counting the moment it is released. See
    ``QuotaLedgerEventType`` for the full reservation/release/reconcile
    contract.

    ``accounting_month``, not ``created_at``, scopes the query: a release
    or worker resize for a reservation that belongs to an earlier month
    must never be counted against (or bleed into) a later month just
    because it was *written* later. Pass ``accounting_month`` explicitly to
    query a specific period (e.g. the original month a reservation being
    resized belongs to); otherwise this defaults to the month derived from
    ``now`` (or the current time).
    """
    target_month = accounting_month if accounting_month is not None else _current_month_start(now).date()
    stmt = select(func.coalesce(func.sum(QuotaLedgerEntry.seconds_delta), 0.0)).where(
        QuotaLedgerEntry.user_id == user_id,
        QuotaLedgerEntry.event_type.in_(
            (
                QuotaLedgerEventType.ANALYSIS_RESERVED,
                QuotaLedgerEventType.ANALYSIS_RESERVATION_RELEASED,
                QuotaLedgerEventType.ANALYSIS_COMPLETED,
            )
        ),
        QuotaLedgerEntry.accounting_month == target_month,
    )
    return float(db.execute(stmt).scalar_one())


def active_analysis_job_count(db: Session, user_id: uuid.UUID) -> int:
    stmt = select(func.count(AnalysisJob.id)).where(
        AnalysisJob.owner_id == user_id,
        AnalysisJob.status.in_(list(ACTIVE_JOB_STATUSES)),
    )
    return int(db.execute(stmt).scalar_one())


def storage_bytes_used(db: Session, user_id: uuid.UUID) -> int:
    """Running ledger balance of storage bytes currently counted against the
    caller: outstanding reservations (declared size, not yet finalized) plus
    actually-counted bytes for finalized/uploaded assets.

    Unlike ``monthly_analysis_seconds_used``, this is an all-time balance
    against a standing occupancy limit, not bucketed by calendar month --
    see the module docstring for why a monthly filter would be unsafe here.
    """
    stmt = select(func.coalesce(func.sum(QuotaLedgerEntry.bytes_delta), 0)).where(
        QuotaLedgerEntry.user_id == user_id,
        QuotaLedgerEntry.event_type.in_(
            (
                QuotaLedgerEventType.STORAGE_RESERVED,
                QuotaLedgerEventType.STORAGE_RESERVATION_RELEASED,
                QuotaLedgerEventType.UPLOAD_FINALIZED,
                QuotaLedgerEventType.STORAGE_RELEASED,
            )
        ),
    )
    return int(db.execute(stmt).scalar_one())


def record_ledger_event(
    db: Session,
    *,
    user_id: uuid.UUID,
    event_type: QuotaLedgerEventType,
    analysis_job_id: uuid.UUID | None = None,
    video_asset_id: uuid.UUID | None = None,
    seconds_delta: float | None = None,
    bytes_delta: int | None = None,
    accounting_month: date | None = None,
) -> QuotaLedgerEntry:
    entry = QuotaLedgerEntry(
        user_id=user_id,
        event_type=event_type,
        analysis_job_id=analysis_job_id,
        video_asset_id=video_asset_id,
        seconds_delta=seconds_delta,
        bytes_delta=bytes_delta,
        accounting_month=accounting_month if accounting_month is not None else current_accounting_month(),
    )
    db.add(entry)
    return entry
