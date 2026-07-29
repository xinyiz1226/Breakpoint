from __future__ import annotations

import json
import math
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models.base import ensure_aware, utcnow
from app.models.enums import (
    JobStatus,
    QuotaLedgerEventType,
    StorageCleanupOperation,
    StorageCleanupStatus,
    TERMINAL_JOB_STATUSES,
)
from app.models.job import AnalysisJob, ExportJob
from app.models.cleanup import StorageCleanupTask
from app.models.project import Project
from app.models.quota import QuotaLedgerEntry
from app.models.rally import Rally, RallyEdit
from app.models.user import User
from app.models.video import VideoAsset
from app.services import quota as quota_service
from app.services import reservations as reservation_service
from app.services import storage_cleanup as storage_cleanup_service
from app.services.analysis_reservation import apply_authoritative_duration
from app.services.media_subprocess import JobCancelled, MediaProcessError
from app.services.media_tools import MediaProbe
from app.services.storage import ObjectStorage

AUTO_INCLUDE_SCORE = 1.7


class MediaTools(Protocol):
    def probe(self, source: Path, *, cancelled=None) -> MediaProbe: ...

    def create_preview_proxy(
        self, source: Path, output: Path, *, cancelled, progress
    ) -> None: ...

    def analyze(
        self, source: Path, output_dir: Path, *, cancelled, progress
    ) -> Path: ...

    def export(
        self, source: Path, selections, output: Path, *, cancelled, progress
    ) -> None: ...


def _lock_user(db: Session, user_id: uuid.UUID) -> None:
    db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()


def _analysis_cancelled(
    factory: sessionmaker,
    job_id: uuid.UUID,
    lease_token: uuid.UUID,
    *,
    touch_heartbeat: bool,
) -> bool:
    with factory() as db:
        row = db.execute(
            select(
                AnalysisJob.status,
                AnalysisJob.cancel_requested_at,
                AnalysisJob.lease_token,
            ).where(
                AnalysisJob.id == job_id,
            )
        ).one_or_none()
        if (
            row is None
            or row.lease_token != lease_token
            or row.status != JobStatus.RUNNING
            or row.cancel_requested_at is not None
        ):
            return True
        if touch_heartbeat:
            job = db.get(AnalysisJob, job_id)
            assert job is not None
            job.heartbeat_at = utcnow()
            db.commit()
        return False


def _export_cancelled(
    factory: sessionmaker,
    job_id: uuid.UUID,
    lease_token: uuid.UUID,
    *,
    touch_heartbeat: bool,
) -> bool:
    with factory() as db:
        row = db.execute(
            select(
                ExportJob.status,
                ExportJob.cancel_requested_at,
                ExportJob.lease_token,
            ).where(
                ExportJob.id == job_id
            )
        ).one_or_none()
        if (
            row is None
            or row.lease_token != lease_token
            or row.status != JobStatus.RUNNING
            or row.cancel_requested_at is not None
        ):
            return True
        if touch_heartbeat:
            job = db.get(ExportJob, job_id)
            assert job is not None
            job.heartbeat_at = utcnow()
            db.commit()
        return False


def _cancellation_probe(check) -> Callable[[], bool]:
    last_heartbeat = 0.0

    def cancelled() -> bool:
        nonlocal last_heartbeat
        now = time.monotonic()
        touch = now - last_heartbeat >= 5
        if touch:
            last_heartbeat = now
        return check(touch)

    return cancelled


def _touch_lease(
    factory: sessionmaker,
    model,
    job_id: uuid.UUID,
    lease_token: uuid.UUID,
) -> bool:
    with factory() as db:
        job = db.execute(
            select(model).where(
                model.id == job_id,
                model.lease_token == lease_token,
                model.status == JobStatus.RUNNING,
                model.cancel_requested_at.is_(None),
            )
        ).scalar_one_or_none()
        if job is None:
            return False
        job.heartbeat_at = utcnow()
        db.commit()
        return True


@contextmanager
def _storage_heartbeat(
    factory: sessionmaker,
    model,
    job_id: uuid.UUID,
    lease_token: uuid.UUID,
    settings: Settings,
):
    if not _touch_lease(factory, model, job_id, lease_token):
        raise JobCancelled()
    stopped = threading.Event()
    interval = max(1.0, min(30.0, settings.job_stale_after_seconds / 3))

    def heartbeat() -> None:
        while not stopped.wait(interval):
            if not _touch_lease(factory, model, job_id, lease_token):
                return

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=interval + 1)


def _progress_value(event: dict) -> tuple[float | None, str | None]:
    event_type = event.get("type")
    if event_type == "step":
        step = float(event.get("step", 0))
        total = max(float(event.get("total", 1)), 1)
        return min(max(step / total, 0.0), 0.95), str(event.get("label", "Analyzing"))[:200]
    if event_type == "progress":
        current = float(event.get("current", 0))
        total = max(float(event.get("sub_total", 1)), 1)
        return min(max(current / total, 0.0), 0.95), None
    if event_type == "complete":
        return 0.95, "Persisting report"
    return None, None


def _update_analysis_progress(
    factory: sessionmaker, job_id: uuid.UUID, lease_token: uuid.UUID, event: dict
) -> None:
    progress, step = _progress_value(event)
    if progress is None and step is None:
        return
    with factory() as db:
        job = db.execute(
            select(AnalysisJob)
            .where(
                AnalysisJob.id == job_id,
                AnalysisJob.lease_token == lease_token,
                AnalysisJob.cancel_requested_at.is_(None),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if job is None or job.status != JobStatus.RUNNING:
            return
        if progress is not None:
            job.progress = progress
        if step is not None:
            job.current_step = step
        job.event_version += 1
        job.heartbeat_at = utcnow()
        db.commit()


def _update_export_progress(
    factory: sessionmaker, job_id: uuid.UUID, lease_token: uuid.UUID, event: dict
) -> None:
    with factory() as db:
        job = db.execute(
            select(ExportJob)
            .where(
                ExportJob.id == job_id,
                ExportJob.lease_token == lease_token,
                ExportJob.cancel_requested_at.is_(None),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if job is None or job.status != JobStatus.RUNNING:
            return
        raw = event.get("progress")
        if isinstance(raw, (int, float)):
            job.progress = min(max(float(raw), 0.0), 0.95)
        job.current_step = str(event.get("label", "Encoding"))[:200]
        job.event_version += 1
        job.heartbeat_at = utcnow()
        db.commit()


def _claim_analysis(factory: sessionmaker, job_id: uuid.UUID, settings: Settings):
    with factory() as db:
        preview = db.get(AnalysisJob, job_id)
        if preview is None:
            return None
        _lock_user(db, preview.owner_id)
        job = db.execute(
            select(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()
        project = db.get(Project, job.project_id)
        if project is None or project.deleted_at is not None:
            _cancel_analysis_locked(db, job, "Cancelled because the project was deleted")
            db.commit()
            return None
        if job.cancel_requested_at is not None:
            _cancel_analysis_locked(db, job, "Analysis cancelled")
            db.commit()
            return None
        stale_before = utcnow() - timedelta(seconds=settings.job_stale_after_seconds)
        running_is_fresh = (
            job.status == JobStatus.RUNNING
            and job.heartbeat_at is not None
            and ensure_aware(job.heartbeat_at) > stale_before
        )
        if job.status in TERMINAL_JOB_STATUSES or running_is_fresh:
            db.commit()
            return None
        lease_token = uuid.uuid4()
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        job.finished_at = None
        job.failure_summary = None
        job.failure_detail = None
        job.worker_version = settings.worker_version
        if job.accounting_month is None:
            asset_for_month = db.get(VideoAsset, job.video_asset_id)
            if asset_for_month is not None:
                job.accounting_month = asset_for_month.analysis_reservation_month
        job.current_step = "Downloading source"
        job.progress = 0.01
        job.event_version += 1
        job.lease_token = lease_token
        job.heartbeat_at = utcnow()
        asset = db.get(VideoAsset, job.video_asset_id)
        source = (
            asset.object_key,
            asset.original_filename,
            job.project_id,
            lease_token,
        ) if asset is not None else None
        db.commit()
        return source


def _record_marker_once(
    db: Session,
    *,
    job: AnalysisJob,
    asset: VideoAsset,
    event_type: QuotaLedgerEventType,
) -> None:
    exists = db.execute(
        select(QuotaLedgerEntry.id).where(
            QuotaLedgerEntry.analysis_job_id == job.id,
            QuotaLedgerEntry.event_type == event_type,
        )
    ).first()
    if exists is None:
        quota_service.record_ledger_event(
            db,
            user_id=job.owner_id,
            event_type=event_type,
            analysis_job_id=job.id,
            video_asset_id=asset.id,
        )


def _cancel_analysis_locked(db: Session, job: AnalysisJob, summary: str) -> None:
    asset = db.get(VideoAsset, job.video_asset_id)
    if asset is not None:
        reservation_service.release_analysis_reservation(db, asset)
        _record_marker_once(
            db,
            job=job,
            asset=asset,
            event_type=QuotaLedgerEventType.ANALYSIS_CANCELLED,
        )
    job.status = JobStatus.CANCELLED
    job.failure_summary = summary[:500]
    job.failure_detail = None
    job.finished_at = utcnow()
    job.event_version += 1


def _finish_analysis_failure(
    factory: sessionmaker,
    job_id: uuid.UUID,
    summary: str,
    detail: str | None,
    settings: Settings,
    lease_token: uuid.UUID,
) -> None:
    with factory() as db:
        preview = db.get(AnalysisJob, job_id)
        if preview is None:
            return
        _lock_user(db, preview.owner_id)
        job = db.execute(
            select(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .where(AnalysisJob.lease_token == lease_token)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if job is None:
            db.commit()
            return
        asset = db.execute(
            select(VideoAsset).where(VideoAsset.id == job.video_asset_id).with_for_update()
        ).scalar_one()
        if job.status == JobStatus.SUCCEEDED or job.status == JobStatus.CANCELLED:
            db.commit()
            return
        reservation_service.release_analysis_reservation(db, asset)
        _record_marker_once(
            db,
            job=job,
            asset=asset,
            event_type=QuotaLedgerEventType.ANALYSIS_FAILED,
        )
        job.status = JobStatus.FAILED
        job.failure_summary = summary[:500]
        job.failure_detail = detail[-settings.job_stderr_max_chars :] if detail else None
        job.finished_at = utcnow()
        job.event_version += 1
        db.commit()


def _finish_analysis_cancelled(
    factory: sessionmaker, job_id: uuid.UUID, lease_token: uuid.UUID
) -> None:
    with factory() as db:
        preview = db.get(AnalysisJob, job_id)
        if preview is None:
            return
        _lock_user(db, preview.owner_id)
        job = db.execute(
            select(AnalysisJob)
            .where(AnalysisJob.id == job_id, AnalysisJob.lease_token == lease_token)
            .with_for_update()
        ).scalar_one_or_none()
        if job is None:
            db.commit()
            return
        if job.status in TERMINAL_JOB_STATUSES:
            db.commit()
            return
        _cancel_analysis_locked(db, job, "Analysis cancelled")
        db.commit()


def _validate_report(path: Path, duration: float) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Analysis report must be a JSON array")
    validated: list[dict] = []
    seen_indexes: set[int] = set()
    for item in payload:
        if not isinstance(item, dict) or item.get("analysis_version") != 2:
            raise ValueError("Unsupported analysis report version")
        source_index = int(item["index"])
        start = float(item["start"])
        end = float(item["end"])
        score = float(item["score"])
        if (
            source_index in seen_indexes
            or not all(math.isfinite(value) for value in (start, end, score))
            or start < 0
            or end <= start
            or end > duration
        ):
            raise ValueError("Analysis report contains an invalid rally range or index")
        features = item.get("features")
        if not isinstance(features, dict):
            raise ValueError("Analysis report rally features must be an object")
        players = item.get("players")
        if players is not None and not isinstance(players, dict):
            raise ValueError("Analysis report rally players must be an object")
        seen_indexes.add(source_index)
        validated.append(
            {
                "source_index": source_index,
                "start": start,
                "end": end,
                "score": score,
                "features": features,
                "players": players,
            }
        )
    return validated


def _create_artifact_cleanup_intent(
    factory: sessionmaker,
    *,
    project_id: uuid.UUID,
    object_key: str,
) -> uuid.UUID:
    with factory() as db:
        task = storage_cleanup_service.get_or_create_cleanup_task(
            db,
            project_id=project_id,
            video_asset_id=None,
            object_key=object_key,
            upload_id=None,
            operation=StorageCleanupOperation.DELETE_OBJECT,
            not_before=utcnow() + timedelta(hours=6),
        )
        db.commit()
        return task.id


def _renew_artifact_cleanup_intent(
    factory: sessionmaker, task_id: uuid.UUID
) -> uuid.UUID:
    with factory() as db:
        task = db.execute(
            select(StorageCleanupTask)
            .where(StorageCleanupTask.id == task_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()
        not_before = utcnow() + timedelta(hours=6)
        if (
            task.status == StorageCleanupStatus.PENDING
            and task.attempts == 0
            and task.lease_token is None
        ):
            task.not_before = not_before
            db.commit()
            return task.id
        successor = storage_cleanup_service.get_or_create_cleanup_task(
            db,
            project_id=task.project_id,
            video_asset_id=None,
            object_key=task.object_key,
            upload_id=None,
            operation=StorageCleanupOperation.DELETE_OBJECT,
            generation=task.generation + 1,
            not_before=not_before,
        )
        db.commit()
        return successor.id


def _claim_artifact_publication(
    db: Session, task_ids: list[uuid.UUID]
) -> bool:
    tasks = db.execute(
        select(StorageCleanupTask)
        .where(StorageCleanupTask.id.in_(task_ids))
        .order_by(StorageCleanupTask.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalars().all()
    pristine = len(tasks) == len(task_ids) and all(
        task.status == StorageCleanupStatus.PENDING
        and task.attempts == 0
        and task.lease_token is None
        for task in tasks
    )
    if pristine:
        for task in tasks:
            task.status = StorageCleanupStatus.CANCELLED
            task.lease_token = uuid.uuid4()
        return True
    for task in tasks:
        storage_cleanup_service.get_or_create_cleanup_task(
            db,
            project_id=task.project_id,
            video_asset_id=None,
            object_key=task.object_key,
            upload_id=None,
            operation=StorageCleanupOperation.DELETE_OBJECT,
            generation=task.generation + 1,
        )
    return False


def process_analysis_job(
    factory: sessionmaker,
    storage: ObjectStorage,
    tools: MediaTools,
    job_id: uuid.UUID,
    *,
    settings: Settings,
) -> None:
    source_info = _claim_analysis(factory, job_id, settings)
    if source_info is None:
        return
    object_key, filename, project_id, lease_token = source_info
    artifact_task_ids: list[uuid.UUID] = []
    try:
        with tempfile.TemporaryDirectory(prefix=f"breakpoint-analysis-{job_id}-") as workspace:
            root = Path(workspace)
            source = root / Path(filename).name
            with _storage_heartbeat(
                factory, AnalysisJob, job_id, lease_token, settings
            ):
                storage.download_file(object_key=object_key, destination=str(source))
            cancelled = _cancellation_probe(
                lambda touch: _analysis_cancelled(
                    factory, job_id, lease_token, touch_heartbeat=touch
                )
            )
            probe = tools.probe(source, cancelled=cancelled)
            authoritative_duration = float(probe.duration_seconds)
            if (
                not math.isfinite(authoritative_duration)
                or authoritative_duration <= 0
            ):
                raise ValueError("Media duration must be finite and greater than zero")
            with factory() as db:
                job = db.execute(
                    select(AnalysisJob).where(
                        AnalysisJob.id == job_id,
                        AnalysisJob.lease_token == lease_token,
                        AnalysisJob.status == JobStatus.RUNNING,
                    )
                ).scalar_one_or_none()
                if job is None:
                    raise JobCancelled()
                reconciled = apply_authoritative_duration(
                    db,
                    video_asset_id=job.video_asset_id,
                    analysis_job_id=job.id,
                    authoritative_duration_seconds=authoritative_duration,
                    settings=settings,
                    commit=False,
                )
                if reconciled.status == JobStatus.FAILED:
                    _record_marker_once(
                        db,
                        job=reconciled,
                        asset=reconciled.video_asset,
                        event_type=QuotaLedgerEventType.ANALYSIS_FAILED,
                    )
                    reconciled.event_version += 1
                    reconciled.finished_at = utcnow()
                    db.commit()
                    return
                reconciled.heartbeat_at = utcnow()
                db.commit()

            progress = lambda event: _update_analysis_progress(
                factory, job_id, lease_token, event
            )
            preview_key: str | None = None
            if not probe.browser_compatible:
                preview_path = root / "preview.mp4"
                tools.create_preview_proxy(
                    source, preview_path, cancelled=cancelled, progress=progress
                )
                preview_key = f"projects/{project_id}/preview/{uuid.uuid4()}.mp4"

            output_dir = root / "analysis"
            output_dir.mkdir()
            report_path = tools.analyze(
                source, output_dir, cancelled=cancelled, progress=progress
            )
            rallies = _validate_report(report_path, authoritative_duration)
            report_key = (
                f"projects/{project_id}/reports/{job_id}/"
                f"{lease_token}/full_report.json"
            )
            artifact_keys = [report_key]
            if preview_key is not None:
                artifact_keys.append(preview_key)
            artifact_task_ids = [
                _create_artifact_cleanup_intent(
                    factory, project_id=project_id, object_key=key
                )
                for key in artifact_keys
            ]
            if preview_key is not None:
                artifact_task_ids[1] = _renew_artifact_cleanup_intent(
                    factory, artifact_task_ids[1]
                )
                with _storage_heartbeat(
                    factory, AnalysisJob, job_id, lease_token, settings
                ):
                    storage.upload_file(
                        source=str(preview_path),
                        object_key=preview_key,
                        content_type="video/mp4",
                    )
            artifact_task_ids[0] = _renew_artifact_cleanup_intent(
                factory, artifact_task_ids[0]
            )
            with _storage_heartbeat(
                factory, AnalysisJob, job_id, lease_token, settings
            ):
                storage.upload_file(
                    source=str(report_path),
                    object_key=report_key,
                    content_type="application/json",
                )
            with factory() as db:
                preview = db.get(AnalysisJob, job_id)
                assert preview is not None
                _lock_user(db, preview.owner_id)
                asset = db.execute(
                    select(VideoAsset)
                    .where(VideoAsset.id == preview.video_asset_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ).scalar_one()
                job = db.execute(
                    select(AnalysisJob)
                    .where(AnalysisJob.id == job_id)
                    .where(AnalysisJob.lease_token == lease_token)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ).scalar_one_or_none()
                if job is None:
                    db.commit()
                    raise JobCancelled()
                project = db.get(Project, project_id)
                if job.cancel_requested_at is not None:
                    _cancel_analysis_locked(db, job, "Analysis cancelled")
                    db.commit()
                    raise JobCancelled()
                if (
                    job.status != JobStatus.RUNNING
                    or project is None
                    or project.deleted_at is not None
                ):
                    db.commit()
                    raise JobCancelled()

                if not _claim_artifact_publication(db, artifact_task_ids):
                    reservation_service.release_analysis_reservation(db, asset)
                    _record_marker_once(
                        db,
                        job=job,
                        asset=asset,
                        event_type=QuotaLedgerEventType.ANALYSIS_FAILED,
                    )
                    job.status = JobStatus.FAILED
                    job.failure_summary = (
                        "Artifact cleanup started before publication; retry the job"
                    )
                    job.failure_detail = None
                    job.finished_at = utcnow()
                    job.event_version += 1
                    db.commit()
                    return
                reservation_month = job.accounting_month or asset.analysis_reservation_month
                duration = float(asset.duration_seconds or 0)
                reservation_service.release_analysis_reservation(db, asset)
                quota_service.record_ledger_event(
                    db,
                    user_id=job.owner_id,
                    event_type=QuotaLedgerEventType.ANALYSIS_COMPLETED,
                    analysis_job_id=job.id,
                    video_asset_id=asset.id,
                    seconds_delta=duration,
                    accounting_month=reservation_month,
                )
                db.execute(delete(Rally).where(Rally.analysis_job_id == job.id))
                for item in rallies:
                    rally = Rally(
                        analysis_job_id=job.id,
                        report_version="2",
                        **item,
                    )
                    db.add(rally)
                    db.flush()
                    db.add(
                        RallyEdit(
                            rally_id=rally.id,
                            included=rally.score > AUTO_INCLUDE_SCORE,
                        )
                    )
                asset.preview_object_key = preview_key
                job.report_object_key = report_key
                job.status = JobStatus.SUCCEEDED
                job.progress = 1.0
                job.current_step = "Complete"
                job.finished_at = utcnow()
                job.failure_summary = None
                job.failure_detail = None
                job.event_version += 1
                db.commit()
    except JobCancelled:
        _finish_analysis_cancelled(factory, job_id, lease_token)
    except MediaProcessError as exc:
        _finish_analysis_failure(
            factory,
            job_id,
            "Media processing failed",
            exc.stderr,
            settings,
            lease_token,
        )
    except Exception as exc:
        _finish_analysis_failure(
            factory, job_id, str(exc), None, settings, lease_token
        )


def process_export_job(
    factory: sessionmaker,
    storage: ObjectStorage,
    tools: MediaTools,
    job_id: uuid.UUID,
    *,
    settings: Settings,
) -> None:
    with factory() as db:
        preview = db.get(ExportJob, job_id)
        if preview is None:
            return
        _lock_user(db, preview.owner_id)
        job = db.execute(
            select(ExportJob)
            .where(ExportJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()
        project = db.get(Project, job.project_id)
        stale_before = utcnow() - timedelta(seconds=settings.job_stale_after_seconds)
        running_is_fresh = (
            job.status == JobStatus.RUNNING
            and job.heartbeat_at is not None
            and ensure_aware(job.heartbeat_at) > stale_before
        )
        if job.status in TERMINAL_JOB_STATUSES or running_is_fresh:
            db.commit()
            return
        if project is None or project.deleted_at is not None:
            job.status = JobStatus.CANCELLED
            job.failure_summary = "Cancelled because the project was deleted"
            job.failure_detail = None
            job.finished_at = utcnow()
            job.event_version += 1
            db.commit()
            return
        if job.cancel_requested_at is not None:
            job.status = JobStatus.CANCELLED
            job.failure_summary = "Export cancelled"
            job.failure_detail = None
            job.finished_at = utcnow()
            job.event_version += 1
            db.commit()
            return
        asset = db.execute(
            select(VideoAsset).where(VideoAsset.project_id == job.project_id)
        ).scalar_one()
        selections = list(job.selection_snapshot)
        duration = float(asset.duration_seconds or 0)
        for selection in selections:
            start = float(selection["start"])
            end = float(selection["end"])
            if start < 0 or end <= start or end > duration:
                job.status = JobStatus.FAILED
                job.failure_summary = "Export selection contains an invalid time range"
                job.finished_at = utcnow()
                job.event_version += 1
                db.commit()
                return
        if not selections:
            job.status = JobStatus.FAILED
            job.failure_summary = "Export requires at least one included rally"
            job.finished_at = utcnow()
            job.event_version += 1
            db.commit()
            return
        lease_token = uuid.uuid4()
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        job.current_step = "Downloading source"
        job.event_version += 1
        job.lease_token = lease_token
        job.heartbeat_at = utcnow()
        source_key = asset.object_key
        filename = asset.original_filename
        project_id = job.project_id
        db.commit()

    uploaded_key: str | None = None
    artifact_task_id: uuid.UUID | None = None
    try:
        with tempfile.TemporaryDirectory(prefix=f"breakpoint-export-{job_id}-") as workspace:
            root = Path(workspace)
            source = root / Path(filename).name
            output = root / "highlights.mp4"
            with _storage_heartbeat(
                factory, ExportJob, job_id, lease_token, settings
            ):
                storage.download_file(object_key=source_key, destination=str(source))
            tools.export(
                source,
                selections,
                output,
                cancelled=_cancellation_probe(
                    lambda touch: _export_cancelled(
                        factory, job_id, lease_token, touch_heartbeat=touch
                    )
                ),
                progress=lambda event: _update_export_progress(
                    factory, job_id, lease_token, event
                ),
            )
            uploaded_key = f"projects/{project_id}/exports/{uuid.uuid4()}.mp4"
            artifact_task_id = _create_artifact_cleanup_intent(
                factory, project_id=project_id, object_key=uploaded_key
            )
            artifact_task_id = _renew_artifact_cleanup_intent(
                factory, artifact_task_id
            )
            with _storage_heartbeat(
                factory, ExportJob, job_id, lease_token, settings
            ):
                storage.upload_file(
                    source=str(output),
                    object_key=uploaded_key,
                    content_type="video/mp4",
                )
            with factory() as db:
                preview = db.get(ExportJob, job_id)
                if preview is None:
                    raise JobCancelled()
                _lock_user(db, preview.owner_id)
                project = db.execute(
                    select(Project)
                    .where(Project.id == project_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ).scalar_one_or_none()
                job = db.execute(
                    select(ExportJob)
                    .where(
                        ExportJob.id == job_id,
                        ExportJob.lease_token == lease_token,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ).scalar_one_or_none()
                if job is None:
                    db.commit()
                    raise JobCancelled()
                if job.cancel_requested_at is not None:
                    job.status = JobStatus.CANCELLED
                    job.failure_summary = "Export cancelled"
                    job.finished_at = utcnow()
                    job.event_version += 1
                    db.commit()
                    raise JobCancelled()
                if (
                    job.status != JobStatus.RUNNING
                    or project is None
                    or project.deleted_at is not None
                ):
                    db.commit()
                    raise JobCancelled()
                assert artifact_task_id is not None
                if not _claim_artifact_publication(db, [artifact_task_id]):
                    job.status = JobStatus.FAILED
                    job.failure_summary = (
                        "Artifact cleanup started before publication; retry the job"
                    )
                    job.failure_detail = None
                    job.finished_at = utcnow()
                    job.event_version += 1
                    db.commit()
                    return
                job.status = JobStatus.SUCCEEDED
                job.progress = 1.0
                job.current_step = "Complete"
                job.output_object_key = uploaded_key
                job.output_expires_at = utcnow() + timedelta(
                    days=settings.asset_retention_days
                )
                job.finished_at = utcnow()
                job.event_version += 1
                db.commit()
                uploaded_key = None
    except JobCancelled:
        with factory() as db:
            preview = db.get(ExportJob, job_id)
            if preview is None:
                return
            _lock_user(db, preview.owner_id)
            job = db.execute(
                select(ExportJob).where(
                    ExportJob.id == job_id,
                    ExportJob.lease_token == lease_token,
                )
            ).scalar_one_or_none()
            if job is not None and job.status not in TERMINAL_JOB_STATUSES:
                job.status = JobStatus.CANCELLED
                job.failure_summary = "Export cancelled"
                job.failure_detail = None
                job.finished_at = utcnow()
                job.event_version += 1
                db.commit()
    except MediaProcessError as exc:
        with factory() as db:
            preview = db.get(ExportJob, job_id)
            if preview is None:
                return
            _lock_user(db, preview.owner_id)
            job = db.execute(
                select(ExportJob).where(
                    ExportJob.id == job_id,
                    ExportJob.lease_token == lease_token,
                )
            ).scalar_one_or_none()
            if job is not None and job.status not in TERMINAL_JOB_STATUSES:
                job.status = JobStatus.FAILED
                job.failure_summary = "Media processing failed"
                job.failure_detail = exc.stderr[-settings.job_stderr_max_chars :]
                job.finished_at = utcnow()
                job.event_version += 1
                db.commit()
    except Exception as exc:
        with factory() as db:
            preview = db.get(ExportJob, job_id)
            if preview is None:
                return
            _lock_user(db, preview.owner_id)
            job = db.execute(
                select(ExportJob).where(
                    ExportJob.id == job_id,
                    ExportJob.lease_token == lease_token,
                )
            ).scalar_one_or_none()
            if job is not None and job.status not in TERMINAL_JOB_STATUSES:
                job.status = JobStatus.FAILED
                job.failure_summary = str(exc)[:500]
                job.failure_detail = None
                job.finished_at = utcnow()
                job.event_version += 1
                db.commit()


__all__ = ["MediaProbe", "process_analysis_job", "process_export_job"]
