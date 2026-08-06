from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, DateTime, Enum, Float, ForeignKey, Index
from sqlalchemy import Uuid as UuidType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import UUIDPrimaryKeyMixin, utcnow
from app.models.enums import QuotaLedgerEventType

if TYPE_CHECKING:
    from app.models.user import User


def current_accounting_month() -> date:
    """First UTC day of the current calendar month.

    The default for ``QuotaLedgerEntry.accounting_month``, and what
    services fall back to when no explicit period is given. Kept separate
    from ``created_at`` -- a release/resize ledger row written "now" for a
    reservation that belongs to an earlier month must still carry that
    earlier month, not today's.
    """
    return datetime.now(timezone.utc).date().replace(day=1)


class QuotaLedgerEntry(UUIDPrimaryKeyMixin, Base):
    """Records usage events (uploaded bytes, analyzed seconds, job counts).

    This supports free quotas now and paid plans later without rewriting the
    processing model. ``analysis_job_id``/``video_asset_id`` are recorded as
    plain UUID columns rather than foreign keys so ledger history survives
    deletion of the underlying job or asset.

    ``accounting_month`` is the period this entry counts against, which is
    independent of ``created_at``: a release or worker resize written after
    a calendar rollover must still carry the *original* reservation's
    month, so monthly aggregation never nets a stale-month event against
    the current month (see ``app.services.quota.monthly_analysis_seconds_used``).
    """

    __tablename__ = "quota_ledger_entries"
    __table_args__ = (
        Index("ix_quota_ledger_entries_user_id_accounting_month", "user_id", "accounting_month"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[QuotaLedgerEventType] = mapped_column(
        Enum(QuotaLedgerEventType, native_enum=False, validate_strings=True, length=32), nullable=False
    )
    analysis_job_id: Mapped[uuid.UUID | None] = mapped_column(UuidType(as_uuid=True), nullable=True)
    video_asset_id: Mapped[uuid.UUID | None] = mapped_column(UuidType(as_uuid=True), nullable=True)
    seconds_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    bytes_delta: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    accounting_month: Mapped[date] = mapped_column(
        Date, default=current_accounting_month, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    user: Mapped["User"] = relationship()
