"""Shared model mixins: UUID primary keys and timezone-aware timestamps."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware(value: datetime) -> datetime:
    """Treat naive datetimes as UTC.

    SQLite (used in tests) does not persist timezone info on ``DateTime``
    columns, so a value written as timezone-aware UTC comes back naive after
    a round trip. Postgres preserves it correctly. Comparisons in model
    properties normalize through this helper so behavior is identical on
    both backends.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
