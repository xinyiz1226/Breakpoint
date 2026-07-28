from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.auth import EmailToken, RefreshSession
    from app.models.project import Project


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # NULL means "use the configured default"; 0 is a valid override
        # meaning "no quota" (see app.services.quota, which distinguishes
        # NULL from 0 via `is not None` rather than truthiness). Negative
        # values would be nonsensical for either limit.
        CheckConstraint(
            "quota_monthly_analysis_seconds_override IS NULL OR quota_monthly_analysis_seconds_override >= 0",
            name="ck_users_quota_monthly_analysis_seconds_override_non_negative",
        ),
        CheckConstraint(
            "quota_max_active_analysis_jobs_override IS NULL OR quota_max_active_analysis_jobs_override >= 0",
            name="ck_users_quota_max_active_analysis_jobs_override_non_negative",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, validate_strings=True, length=16),
        default=UserRole.USER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Per-user quota overrides. NULL means "use the configured default".
    quota_monthly_analysis_seconds_override: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    quota_max_active_analysis_jobs_override: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    refresh_sessions: Mapped[list["RefreshSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    email_tokens: Mapped[list["EmailToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
