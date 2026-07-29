from __future__ import annotations

import json
import time
import uuid
from collections.abc import Generator

from sqlalchemy import select

from app.models.job import AnalysisJob, ExportJob


def iter_job_events(
    session_factory,
    *,
    job_kind: str,
    job_id: uuid.UUID,
    owner_id: uuid.UUID,
    last_event_id: int,
    poll_seconds: float = 1.0,
    max_events: int | None = None,
) -> Generator[str, None, None]:
    emitted = 0
    while max_events is None or emitted < max_events:
        model = AnalysisJob if job_kind == "analysis" else ExportJob
        with session_factory() as db:
            job = db.execute(
                select(model).where(model.id == job_id, model.owner_id == owner_id)
            ).scalar_one_or_none()
            if job is None:
                return
            version = job.event_version
            payload = {
                "id": str(job.id),
                "status": job.status.value,
                "progress": job.progress,
                "current_step": job.current_step,
                "failure_summary": job.failure_summary,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            }
            terminal = job.status.value in {"succeeded", "failed", "cancelled"}
        if version > last_event_id:
            body = json.dumps(payload, separators=(",", ":"))
            yield f"id: {version}\nevent: progress\ndata: {body}\n\n"
            last_event_id = version
            emitted += 1
            if terminal:
                return
            continue
        if terminal:
            return
        if max_events == 0:
            return
        time.sleep(poll_seconds)
