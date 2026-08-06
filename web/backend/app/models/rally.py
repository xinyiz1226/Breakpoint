from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy import Uuid as UuidType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.job import AnalysisJob


class Rally(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One analyzed rally from the engine report.

    Field names mirror the desktop report/rally convention:
    ``source_index``, ``start``, ``end``, ``score``, ``features``,
    ``players``, ``report_version``.
    """

    __tablename__ = "rallies"
    __table_args__ = (
        UniqueConstraint("analysis_job_id", "source_index", name="uq_rally_job_source_index"),
    )

    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start: Mapped[float] = mapped_column(Float, nullable=False)
    end: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    features: Mapped[dict] = mapped_column(JSON, nullable=False)
    players: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report_version: Mapped[str] = mapped_column(String(32), nullable=False)

    analysis_job: Mapped["AnalysisJob"] = relationship(back_populates="rallies")
    edit: Mapped["RallyEdit | None"] = relationship(
        back_populates="rally", cascade="all, delete-orphan", uselist=False
    )


class RallyEdit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """User review state for a rally, autosaved by the review UI.

    Field names mirror the desktop edit convention: ``included``,
    ``adjusted_start``, ``adjusted_end``.
    """

    __tablename__ = "rally_edits"

    rally_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(as_uuid=True), ForeignKey("rallies.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    included: Mapped[bool] = mapped_column(default=True, nullable=False)
    adjusted_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjusted_end: Mapped[float | None] = mapped_column(Float, nullable=True)

    rally: Mapped["Rally"] = relationship(back_populates="edit")
