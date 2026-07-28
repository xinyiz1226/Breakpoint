from __future__ import annotations

from pydantic import BaseModel


class QuotaRead(BaseModel):
    monthly_analysis_seconds_limit: int
    monthly_analysis_seconds_used: float
    monthly_analysis_seconds_remaining: float
    max_active_analysis_jobs: int
    active_analysis_job_count: int
