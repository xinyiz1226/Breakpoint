from __future__ import annotations

import json
import math
import os
import signal
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import date
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.enums import JobStatus, QuotaLedgerEventType, VideoAssetStatus
from app.models.cleanup import StorageCleanupTask
from app.models.enums import StorageCleanupStatus
from app.models.job import AnalysisJob, ExportJob
from app.models.project import Project
from app.models.quota import QuotaLedgerEntry
from app.models.rally import Rally
from app.models.video import VideoAsset
from app.services import media_processing as media_processing_service
from app.services.media_processing import (
    MediaProbe,
    process_analysis_job,
    process_export_job,
)
from app.services.media_subprocess import (
    JobCancelled,
    MediaProcessError,
    run_json_progress_process,
)
from app.services.storage import ObjectMetadata
from app.services.storage_cleanup import run_due_storage_cleanup_sweep
from app.models.base import utcnow
from app.services.media_tools import RealMediaTools
from tests.conftest import create_user
from tests.fakes import FakeObjectStorage


@dataclass
class FakeMediaTools:
    probe_result: MediaProbe
    report: list[dict]
    cancelled: bool = False
    analyze_calls: int = 0
    proxy_calls: int = 0

    def probe(self, source: Path, *, cancelled=None) -> MediaProbe:
        return self.probe_result

    def create_preview_proxy(self, source: Path, output: Path, *, cancelled, progress) -> None:
        self.proxy_calls += 1
        output.write_bytes(b"proxy")

    def analyze(self, source: Path, output_dir: Path, *, cancelled, progress) -> Path:
        self.analyze_calls += 1
        if self.cancelled:
            from app.services.media_subprocess import JobCancelled

            raise JobCancelled()
        report_path = output_dir / "full_report.json"
        report_path.write_text(json.dumps(self.report), encoding="utf-8")
        return report_path

    def export(self, source: Path, selections, output: Path, *, cancelled, progress) -> None:
        output.write_bytes(b"export")


def _create_analysis_job(
    db: Session,
    storage: FakeObjectStorage,
    *,
    declared_duration: float = 120.0,
    reservation_month: date = date(2026, 1, 1),
) -> AnalysisJob:
    owner = create_user(
        db, email=f"{uuid.uuid4().hex}@example.com", password="Test-password-123"
    )
    project = Project(owner_id=owner.id, name="Match")
    db.add(project)
    db.flush()
    asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key=f"projects/{project.id}/source/match.mov",
        original_filename="match.mov",
        content_type="video/quicktime",
        declared_size_bytes=5,
        actual_size_bytes=5,
        declared_duration_seconds=declared_duration,
        status=VideoAssetStatus.UPLOADED,
        upload_id="upload",
        part_count=1,
        analysis_reserved_seconds=declared_duration,
        analysis_reservation_month=reservation_month,
        storage_counted_bytes=5,
    )
    db.add(asset)
    db.flush()
    from app.services import quota

    quota.record_ledger_event(
        db,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        video_asset_id=asset.id,
        seconds_delta=declared_duration,
        accounting_month=reservation_month,
    )
    job = AnalysisJob(
        project_id=project.id,
        video_asset_id=asset.id,
        owner_id=owner.id,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    db.commit()
    storage.put_bytes(
        object_key=asset.object_key,
        data=b"video",
        content_type=asset.content_type,
    )
    return job


def _report() -> list[dict]:
    return [
        {
            "analysis_version": 2,
            "index": 1,
            "start": 10.0,
            "end": 20.0,
            "score": 2.1,
            "features": {"hit_count": 4},
        },
        {
            "analysis_version": 2,
            "index": 2,
            "start": 30.0,
            "end": 40.0,
            "score": 1.0,
            "features": {"hit_count": 2},
        },
    ]


def test_analysis_reconciles_billing_persists_report_and_creates_proxy_only_when_needed(
    session_factory, db_session: Session, fake_storage: FakeObjectStorage, test_settings: Settings
) -> None:
    job = _create_analysis_job(db_session, fake_storage)
    tools = FakeMediaTools(
        probe_result=MediaProbe(
            duration_seconds=150.0,
            container="mov",
            video_codec="prores",
            audio_codec="pcm_s16le",
        ),
        report=_report(),
    )

    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )

    db_session.expire_all()
    persisted = db_session.get(AnalysisJob, job.id)
    assert persisted.status == JobStatus.SUCCEEDED
    assert persisted.progress == 1.0
    assert persisted.report_object_key in fake_storage.objects
    assert persisted.video_asset.preview_object_key in fake_storage.objects
    assert tools.proxy_calls == 1
    rallies = db_session.execute(
        select(Rally).where(Rally.analysis_job_id == job.id).order_by(Rally.source_index)
    ).scalars().all()
    assert [r.edit.included for r in rallies] == [True, False]

    entries = db_session.execute(
        select(QuotaLedgerEntry).where(
            QuotaLedgerEntry.video_asset_id == persisted.video_asset_id
        )
    ).scalars().all()
    assert [entry.event_type for entry in entries].count(
        QuotaLedgerEventType.ANALYSIS_COMPLETED
    ) == 1
    completed = next(
        entry
        for entry in entries
        if entry.event_type == QuotaLedgerEventType.ANALYSIS_COMPLETED
    )
    assert completed.seconds_delta == 150.0
    assert completed.accounting_month == date(2026, 1, 1)
    assert persisted.video_asset.analysis_reserved_seconds == 0.0

    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )
    db_session.expire_all()
    entries = db_session.execute(
        select(QuotaLedgerEntry).where(
            QuotaLedgerEntry.video_asset_id == persisted.video_asset_id
        )
    ).scalars().all()
    assert [entry.event_type for entry in entries].count(
        QuotaLedgerEventType.ANALYSIS_COMPLETED
    ) == 1
    assert tools.analyze_calls == 1


def test_authoritative_duration_rejection_never_runs_engine(
    session_factory, db_session: Session, fake_storage: FakeObjectStorage, test_settings: Settings
) -> None:
    job = _create_analysis_job(db_session, fake_storage)
    tools = FakeMediaTools(
        probe_result=MediaProbe(
            duration_seconds=test_settings.max_video_duration_seconds + 1,
            container="mp4",
            video_codec="h264",
            audio_codec="aac",
        ),
        report=_report(),
    )

    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )

    db_session.expire_all()
    persisted = db_session.get(AnalysisJob, job.id)
    assert persisted.status == JobStatus.FAILED
    assert persisted.video_asset.analysis_reserved_seconds == 0
    assert tools.analyze_calls == 0


@pytest.mark.parametrize(
    "duration", [-1.0, 0.0, math.nan, math.inf, -math.inf]
)
def test_invalid_authoritative_duration_fails_without_persisting_invalid_state(
    duration: float,
    session_factory,
    db_session: Session,
    fake_storage: FakeObjectStorage,
    test_settings: Settings,
) -> None:
    job = _create_analysis_job(db_session, fake_storage)
    tools = FakeMediaTools(
        probe_result=MediaProbe(duration, "mp4", "h264", "aac"),
        report=_report(),
    )

    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )
    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )

    db_session.expire_all()
    persisted = db_session.get(AnalysisJob, job.id)
    assert persisted.status == JobStatus.FAILED
    assert persisted.video_asset.duration_seconds is None
    assert persisted.video_asset.duration_status is None
    assert persisted.video_asset.analysis_reserved_seconds == 0
    assert tools.analyze_calls == 0
    entries = db_session.execute(
        select(QuotaLedgerEntry).where(
            QuotaLedgerEntry.video_asset_id == persisted.video_asset_id
        )
    ).scalars().all()
    assert [entry.event_type for entry in entries].count(
        QuotaLedgerEventType.ANALYSIS_RESERVATION_RELEASED
    ) == 1
    assert all(
        entry.seconds_delta is None or math.isfinite(entry.seconds_delta)
        for entry in entries
    )


def test_cancelled_analysis_releases_reservation_once(
    session_factory, db_session: Session, fake_storage: FakeObjectStorage, test_settings: Settings
) -> None:
    job = _create_analysis_job(db_session, fake_storage)
    tools = FakeMediaTools(
        probe_result=MediaProbe(120, "mp4", "h264", "aac"),
        report=_report(),
        cancelled=True,
    )

    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )
    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )

    db_session.expire_all()
    persisted = db_session.get(AnalysisJob, job.id)
    assert persisted.status == JobStatus.CANCELLED
    assert persisted.video_asset.analysis_reserved_seconds == 0
    entries = db_session.execute(
        select(QuotaLedgerEntry).where(QuotaLedgerEntry.analysis_job_id == job.id)
    ).scalars().all()
    assert [entry.event_type for entry in entries].count(
        QuotaLedgerEventType.ANALYSIS_CANCELLED
    ) == 1


def test_progress_callbacks_do_not_refresh_cancelled_job_leases(
    session_factory,
    db_session: Session,
    fake_storage: FakeObjectStorage,
) -> None:
    analysis = _create_analysis_job(db_session, fake_storage)
    analysis_lease = uuid.uuid4()
    analysis.status = JobStatus.RUNNING
    analysis.lease_token = analysis_lease
    analysis.cancel_requested_at = utcnow()
    export = ExportJob(
        project_id=analysis.project_id,
        owner_id=analysis.owner_id,
        status=JobStatus.RUNNING,
        lease_token=uuid.uuid4(),
        cancel_requested_at=utcnow(),
        selection_snapshot=[],
    )
    db_session.add(export)
    db_session.commit()

    media_processing_service._update_analysis_progress(
        session_factory,
        analysis.id,
        analysis_lease,
        {"type": "step", "step": 1, "total": 2},
    )
    media_processing_service._update_export_progress(
        session_factory,
        export.id,
        export.lease_token,
        {"progress": 0.5},
    )

    db_session.expire_all()
    assert db_session.get(AnalysisJob, analysis.id).event_version == 0
    assert db_session.get(AnalysisJob, analysis.id).progress == 0
    assert db_session.get(ExportJob, export.id).event_version == 0
    assert db_session.get(ExportJob, export.id).progress == 0


def test_browser_compatible_media_skips_proxy(
    session_factory, db_session: Session, fake_storage: FakeObjectStorage, test_settings: Settings
) -> None:
    job = _create_analysis_job(db_session, fake_storage)
    tools = FakeMediaTools(
        probe_result=MediaProbe(
            duration_seconds=120.0,
            container="mov,mp4,m4a,3gp,3g2,mj2",
            video_codec="h264",
            audio_codec="aac",
        ),
        report=_report(),
    )

    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )

    assert tools.proxy_calls == 0


def test_export_worker_uses_persisted_selection_snapshot(
    session_factory, db_session: Session, fake_storage: FakeObjectStorage, test_settings: Settings
) -> None:
    analysis = _create_analysis_job(db_session, fake_storage)
    asset = analysis.video_asset
    asset.duration_seconds = 120
    export = ExportJob(
        project_id=analysis.project_id,
        owner_id=analysis.owner_id,
        status=JobStatus.QUEUED,
        selection_snapshot=[
            {"rally_id": str(uuid.uuid4()), "start": 11.0, "end": 19.0}
        ],
    )
    db_session.add(export)
    db_session.commit()
    tools = FakeMediaTools(
        probe_result=MediaProbe(120, "mp4", "h264", "aac"),
        report=[],
    )

    process_export_job(
        session_factory, fake_storage, tools, export.id, settings=test_settings
    )

    db_session.expire_all()
    persisted = db_session.get(ExportJob, export.id)
    assert persisted.status == JobStatus.SUCCEEDED
    assert persisted.output_object_key in fake_storage.objects
    assert persisted.selection_snapshot[0]["start"] == 11.0


def test_progress_parser_bounds_stderr_and_ignores_non_json() -> None:
    events: list[dict] = []
    command = [
        sys.executable,
        "-c",
        (
            "import sys; "
            "print('not-json', flush=True); "
            "print('{\"type\":\"step\",\"step\":1,\"total\":2}', flush=True); "
            "print('x' * 200, file=sys.stderr, flush=True); "
            "raise SystemExit(3)"
        ),
    ]

    try:
        run_json_progress_process(
            command,
            cancelled=lambda: False,
            progress=events.append,
            stderr_max_chars=40,
            progress_line_max_chars=100,
        )
    except MediaProcessError as exc:
        assert len(exc.stderr) <= 40
    else:
        raise AssertionError("process failure was not reported")
    assert events == [{"type": "step", "step": 1, "total": 2}]


def test_cancellation_actively_terminates_child_process() -> None:
    started = time.monotonic()

    try:
        run_json_progress_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cancelled=lambda: time.monotonic() - started > 0.2,
            progress=lambda event: None,
        )
    except JobCancelled:
        pass
    else:
        raise AssertionError("cancelled process returned normally")

    assert time.monotonic() - started < 6


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group regression")
def test_cancellation_kills_grandchild_that_ignores_sigterm(tmp_path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    script = (
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-c',"
        "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)']); "
        f"open({str(pid_file)!r},'w').write(str(p.pid)); "
        "time.sleep(30)"
    )
    grandchild_pid: int | None = None
    try:
        with pytest.raises(JobCancelled):
            run_json_progress_process(
                [sys.executable, "-c", script],
                cancelled=pid_file.exists,
                progress=lambda event: None,
            )
        grandchild_pid = int(pid_file.read_text())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(grandchild_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("grandchild survived process-group cancellation")
    finally:
        if grandchild_pid is not None:
            try:
                os.kill(grandchild_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_interrupted_analysis_uses_durable_cleanup_for_uploaded_artifacts(
    session_factory, db_session: Session, fake_storage: FakeObjectStorage, test_settings: Settings
) -> None:
    job = _create_analysis_job(db_session, fake_storage)
    tools = FakeMediaTools(
        probe_result=MediaProbe(120, "mov", "prores", "pcm_s16le"),
        report=_report(),
    )
    fake_storage.fail_next_deletes = 1
    original_upload = fake_storage.upload_file
    upload_count = 0

    def cancel_after_upload(**kwargs):
        nonlocal upload_count
        original_upload(**kwargs)
        upload_count += 1
        if upload_count == 2:
            with session_factory() as session:
                persisted = session.get(AnalysisJob, job.id)
                persisted.cancel_requested_at = utcnow()
                session.commit()

    fake_storage.upload_file = cancel_after_upload

    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )

    db_session.expire_all()
    assert db_session.get(AnalysisJob, job.id).status == JobStatus.CANCELLED
    cleanup_tasks = db_session.execute(
        select(StorageCleanupTask).where(StorageCleanupTask.video_asset_id.is_(None))
    ).scalars().all()
    assert any(task.status == StorageCleanupStatus.PENDING for task in cleanup_tasks)

    run_due_storage_cleanup_sweep(
        db_session, fake_storage, now=utcnow() + timedelta(hours=7)
    )
    db_session.expire_all()
    assert any(
        task.status == StorageCleanupStatus.FAILED
        for task in db_session.execute(
            select(StorageCleanupTask).where(StorageCleanupTask.video_asset_id.is_(None))
        ).scalars()
    )
    run_due_storage_cleanup_sweep(
        db_session, fake_storage, now=utcnow() + timedelta(hours=8)
    )
    db_session.expire_all()
    assert all(
        task.status == StorageCleanupStatus.COMPLETED
        for task in db_session.execute(
            select(StorageCleanupTask).where(StorageCleanupTask.video_asset_id.is_(None))
        ).scalars()
    )


def test_cleanup_claim_wins_over_paused_artifact_publication(
    session_factory,
    db_session: Session,
    fake_storage: FakeObjectStorage,
    test_settings: Settings,
) -> None:
    job = _create_analysis_job(db_session, fake_storage)
    tools = FakeMediaTools(
        probe_result=MediaProbe(120, "mp4", "h264", "aac"),
        report=_report(),
    )
    original_upload = fake_storage.upload_file

    def sweep_after_upload(**kwargs):
        original_upload(**kwargs)
        with session_factory() as session:
            run_due_storage_cleanup_sweep(
                session, fake_storage, now=utcnow() + timedelta(hours=7)
            )

    fake_storage.upload_file = sweep_after_upload

    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )

    db_session.expire_all()
    persisted = db_session.get(AnalysisJob, job.id)
    assert persisted.status == JobStatus.FAILED
    assert persisted.report_object_key is None
    tasks = db_session.execute(
        select(StorageCleanupTask).where(StorageCleanupTask.video_asset_id.is_(None))
    ).scalars().all()
    assert tasks
    assert any(task.status == StorageCleanupStatus.COMPLETED for task in tasks)
    assert any(task.status == StorageCleanupStatus.PENDING for task in tasks)
    run_due_storage_cleanup_sweep(
        db_session, fake_storage, now=utcnow() + timedelta(hours=8)
    )
    db_session.expire_all()
    tasks = db_session.execute(
        select(StorageCleanupTask).where(StorageCleanupTask.video_asset_id.is_(None))
    ).scalars().all()
    assert all(task.status == StorageCleanupStatus.COMPLETED for task in tasks)
    assert all(task.object_key not in fake_storage.objects for task in tasks)


def test_completed_cleanup_before_upload_gets_successor_intent(
    monkeypatch,
    session_factory,
    db_session: Session,
    fake_storage: FakeObjectStorage,
    test_settings: Settings,
) -> None:
    job = _create_analysis_job(db_session, fake_storage)
    tools = FakeMediaTools(
        probe_result=MediaProbe(120, "mp4", "h264", "aac"),
        report=_report(),
    )
    original_create = media_processing_service._create_artifact_cleanup_intent

    def create_after_pause(*args, **kwargs):
        task_id = original_create(*args, **kwargs)
        with session_factory() as session:
            run_due_storage_cleanup_sweep(
                session, fake_storage, now=utcnow() + timedelta(hours=7)
            )
        return task_id

    monkeypatch.setattr(
        media_processing_service,
        "_create_artifact_cleanup_intent",
        create_after_pause,
    )

    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )

    db_session.expire_all()
    persisted = db_session.get(AnalysisJob, job.id)
    assert persisted.status == JobStatus.SUCCEEDED
    assert persisted.report_object_key in fake_storage.objects
    tasks = db_session.execute(
        select(StorageCleanupTask).where(StorageCleanupTask.video_asset_id.is_(None))
    ).scalars().all()
    assert [task.status for task in tasks].count(StorageCleanupStatus.COMPLETED) == 1
    assert [task.status for task in tasks].count(StorageCleanupStatus.CANCELLED) == 1


def test_stale_running_analysis_is_reclaimed_with_a_new_lease(
    session_factory, db_session: Session, fake_storage: FakeObjectStorage, test_settings: Settings
) -> None:
    job = _create_analysis_job(db_session, fake_storage)
    old_lease = uuid.uuid4()
    job.status = JobStatus.RUNNING
    job.lease_token = old_lease
    job.heartbeat_at = utcnow() - timedelta(
        seconds=test_settings.job_stale_after_seconds + 1
    )
    db_session.commit()
    tools = FakeMediaTools(
        probe_result=MediaProbe(120, "mp4", "h264", "aac"),
        report=_report(),
    )

    process_analysis_job(
        session_factory, fake_storage, tools, job.id, settings=test_settings
    )

    db_session.expire_all()
    persisted = db_session.get(AnalysisJob, job.id)
    assert persisted.status == JobStatus.SUCCEEDED
    assert persisted.lease_token != old_lease


def test_unexpected_export_failure_is_durable(
    session_factory, db_session: Session, fake_storage: FakeObjectStorage, test_settings: Settings
) -> None:
    analysis = _create_analysis_job(db_session, fake_storage)
    analysis.video_asset.duration_seconds = 120
    export = ExportJob(
        project_id=analysis.project_id,
        owner_id=analysis.owner_id,
        status=JobStatus.QUEUED,
        selection_snapshot=[
            {"rally_id": str(uuid.uuid4()), "start": 1.0, "end": 2.0}
        ],
    )
    db_session.add(export)
    db_session.commit()
    tools = FakeMediaTools(
        probe_result=MediaProbe(120, "mp4", "h264", "aac"),
        report=[],
    )

    def fail_export(*args, **kwargs):
        raise RuntimeError("storage-adjacent failure")

    tools.export = fail_export
    process_export_job(
        session_factory, fake_storage, tools, export.id, settings=test_settings
    )

    db_session.expire_all()
    persisted = db_session.get(ExportJob, export.id)
    assert persisted.status == JobStatus.FAILED
    assert persisted.failure_summary == "storage-adjacent failure"


def test_worker_terminalizes_export_for_tombstoned_project(
    session_factory, db_session: Session, fake_storage: FakeObjectStorage, test_settings: Settings
) -> None:
    analysis = _create_analysis_job(db_session, fake_storage)
    analysis.video_asset.duration_seconds = 120
    analysis.project.deleted_at = utcnow()
    export = ExportJob(
        project_id=analysis.project_id,
        owner_id=analysis.owner_id,
        status=JobStatus.QUEUED,
        selection_snapshot=[
            {"rally_id": str(uuid.uuid4()), "start": 1.0, "end": 2.0}
        ],
    )
    db_session.add(export)
    db_session.commit()
    tools = FakeMediaTools(
        probe_result=MediaProbe(120, "mp4", "h264", "aac"),
        report=[],
    )

    process_export_job(
        session_factory, fake_storage, tools, export.id, settings=test_settings
    )

    db_session.expire_all()
    assert db_session.get(ExportJob, export.id).status == JobStatus.CANCELLED


def test_real_export_handles_video_without_audio(tmp_path, test_settings: Settings) -> None:
    tools = RealMediaTools(test_settings)
    commands: list[list[str]] = []
    tools.probe = lambda source: MediaProbe(10, "mp4", "h264", None)
    tools._run = lambda command, **kwargs: commands.append(command) or ""

    tools.export(
        tmp_path / "silent.mp4",
        [{"start": 1.0, "end": 2.0}],
        tmp_path / "out.mp4",
        cancelled=lambda: False,
        progress=lambda event: None,
    )

    command = commands[0]
    assert "[outa]" not in command
    assert any("a=0[outv]" in argument for argument in command)
