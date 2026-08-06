"""Worker-facing analysis-reservation reconciliation service.

This is the explicit public "next layer" service seam: the (not-yet-
implemented) analysis worker calls ``apply_authoritative_duration`` after
ffprobing a finalized asset's real duration, before running analysis. It is
the single place that resizes the provisional analysis-seconds reservation
made at upload-initiate time (see ``QuotaLedgerEventType``) to the
authoritative value, and validates that authoritative value against both
the per-video duration cap and the monthly quota -- excluding this asset's
own current reservation, so growing/shrinking one asset's reservation is
judged against the user's other bookings, not against itself.

Locking discipline matches the rest of this layer: lock ``User`` first,
then the ``VideoAsset``/``AnalysisJob`` rows, before any read that feeds a
quota decision or any write.

Idempotency: replaying the same authoritative duration for an asset that
has already recorded that exact duration is a no-op (no duplicate ledger
entries, no re-validation side effects) -- the durable
``VideoAsset.duration_seconds``/``duration_status`` pair, not ledger
history, is what a replay is checked against.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.enums import JobStatus, QuotaLedgerEventType, VideoDurationStatus
from app.models.job import AnalysisJob
from app.models.quota import current_accounting_month
from app.models.user import User
from app.models.video import VideoAsset
from app.services import quota as quota_service
from app.services.reservations import release_analysis_reservation


def apply_authoritative_duration(
    db: Session,
    *,
    video_asset_id: uuid.UUID,
    analysis_job_id: uuid.UUID,
    authoritative_duration_seconds: float,
    settings: Settings,
    commit: bool = True,
) -> AnalysisJob:
    # Non-locking lookup only to identify the owning user, per the same
    # lock-user-first discipline used across this codebase.
    preview_asset = db.execute(
        select(VideoAsset).where(VideoAsset.id == video_asset_id)
    ).scalar_one()

    user = db.execute(
        select(User).where(User.id == preview_asset.owner_id).with_for_update()
    ).scalar_one()

    # populate_existing=True: these rows may already be present in this
    # session's identity map (e.g. from an earlier lookup in a longer-lived
    # caller, or a stale preload in a test), and a concurrent commit from
    # another session that already reconciled this exact asset/job must be
    # observed here rather than returning stale in-memory attributes --
    # otherwise the idempotency check below could miss and this call would
    # redundantly release/re-reserve using stale figures.
    video_asset = db.execute(
        select(VideoAsset)
        .where(VideoAsset.id == video_asset_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    job = db.execute(
        select(AnalysisJob)
        .where(AnalysisJob.id == analysis_job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()

    if job.video_asset_id != video_asset.id or job.owner_id != user.id:
        raise ValueError(
            "analysis_job_id does not belong to the given video_asset_id/owner"
        )

    # Idempotent replay: this exact authoritative duration has already been
    # recorded and reconciled for this asset. Ledger entries and job status
    # were already written by the earlier call; do not repeat them.
    if (
        video_asset.duration_status is not None
        and video_asset.duration_seconds == authoritative_duration_seconds
    ):
        return job

    video_asset.duration_seconds = authoritative_duration_seconds

    # Capture the reservation's original accounting period *before* release
    # clears it: every quota check and ledger write below for this resize
    # must target the month the reservation actually belongs to, never the
    # wall-clock month the worker happens to run in. Existing reservations
    # made without an explicit month (pre-rollover-fix rows, or tests that
    # don't set one) fall back to the current month, preserving prior
    # implicit-current-month behavior exactly.
    original_month = video_asset.analysis_reservation_month or current_accounting_month()

    if authoritative_duration_seconds > settings.max_video_duration_seconds:
        video_asset.duration_status = VideoDurationStatus.EXCEEDED
        release_analysis_reservation(db, video_asset)
        job.status = JobStatus.FAILED
        job.failure_summary = (
            f"Video duration ({authoritative_duration_seconds:.0f}s) exceeds the "
            f"{settings.max_video_duration_seconds}s duration cap"
        )
        if commit:
            db.commit()
        return job

    # Quota excluding this asset's own current reservation: it is about to
    # be released and replaced below, so it must not count against itself.
    # Scoped to the reservation's original month so an unrelated reservation
    # in a different month (before or after rollover) never affects this
    # decision.
    used_excluding_self = (
        quota_service.monthly_analysis_seconds_used(db, user.id, accounting_month=original_month)
        - video_asset.analysis_reserved_seconds
    )
    limit = quota_service.monthly_analysis_seconds_limit(user, settings)

    if used_excluding_self + authoritative_duration_seconds > limit:
        video_asset.duration_status = VideoDurationStatus.WITHIN_LIMIT
        release_analysis_reservation(db, video_asset)
        job.status = JobStatus.FAILED
        job.failure_summary = "Monthly analysis-seconds quota exceeded for this video's actual duration"
        if commit:
            db.commit()
        return job

    # Allowed: resize the reservation to the authoritative amount (release
    # the old provisional booking, reserve the real one) and leave the job
    # queued/ready for analysis. Both legs of the resize -- the release
    # above and the re-reservation below -- target the same original month,
    # so the reservation's period survives the resize unchanged.
    release_analysis_reservation(db, video_asset)
    quota_service.record_ledger_event(
        db,
        user_id=user.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        video_asset_id=video_asset.id,
        seconds_delta=authoritative_duration_seconds,
        accounting_month=original_month,
    )
    video_asset.analysis_reserved_seconds = authoritative_duration_seconds
    video_asset.analysis_reservation_month = original_month
    video_asset.duration_status = VideoDurationStatus.WITHIN_LIMIT

    if commit:
        db.commit()
    return job
