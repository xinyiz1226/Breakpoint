from __future__ import annotations

import uuid
import logging

logger = logging.getLogger(__name__)


def enqueue_analysis_job(job_id: uuid.UUID) -> bool:
    try:
        from app.tasks import analysis_task

        analysis_task.delay(str(job_id))
    except Exception:
        logger.exception("Analysis dispatch failed; Beat will retry queued job %s", job_id)
        return False
    return True


def enqueue_export_job(job_id: uuid.UUID) -> bool:
    try:
        from app.tasks import export_task

        export_task.delay(str(job_id))
    except Exception:
        logger.exception("Export dispatch failed; Beat will retry queued job %s", job_id)
        return False
    return True
