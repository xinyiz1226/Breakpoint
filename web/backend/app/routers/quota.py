"""Quota read endpoint: current usage and effective limits for the caller."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.quota import QuotaRead
from app.services import quota as quota_service

router = APIRouter(prefix="/api/v1/quota", tags=["quota"])


@router.get("/me", response_model=QuotaRead)
def get_my_quota(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> QuotaRead:
    limit = quota_service.monthly_analysis_seconds_limit(current_user, settings)
    used = quota_service.monthly_analysis_seconds_used(db, current_user.id)
    storage_limit = quota_service.storage_bytes_limit(current_user, settings)
    storage_used = quota_service.storage_bytes_used(db, current_user.id)
    return QuotaRead(
        monthly_analysis_seconds_limit=limit,
        monthly_analysis_seconds_used=used,
        monthly_analysis_seconds_remaining=max(limit - used, 0.0),
        max_active_analysis_jobs=quota_service.max_active_analysis_jobs(current_user, settings),
        active_analysis_job_count=quota_service.active_analysis_job_count(db, current_user.id),
        storage_bytes_limit=storage_limit,
        storage_bytes_used=storage_used,
        storage_bytes_remaining=max(storage_limit - storage_used, 0),
    )
