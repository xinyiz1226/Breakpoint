from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey
from sqlalchemy import Uuid as UuidType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import UUIDPrimaryKeyMixin, utcnow
from app.models.enums import QuotaLedgerEventType

if TYPE_CHECKING:
    from app.models.user import User


class QuotaLedgerEntry(UUIDPrimaryKeyMixin, Base):
    """Records usage events (uploaded bytes, analyzed seconds, job counts).

    This supports free quotas now and paid plans later without rewriting the
    processing model. ``analysis_job_id``/``video_asset_id`` are recorded as
    plain UUID columns rather than foreign keys so ledger history survives
    deletion of the underlying job or asset.
    """

    __tablename__ = "quota_ledger_entries"

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    user: Mapped["User"] = relationship()
