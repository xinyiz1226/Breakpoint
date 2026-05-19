import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.models.project import Project, Segment, ProjectStatus
from app.services.analysis_service import run_engine_export
from app.tasks.celery_app import celery_app


def _get_sync_engine():
    url = settings.database_url
    url = url.replace("+asyncpg", "").replace("+aiosqlite", "")
    return create_engine(url, echo=False)


@celery_app.task(bind=True)
def export_highlights(self, project_id: str, video_local_path: str, upload_callback_key: str):
    engine = _get_sync_engine()
    with Session(engine) as db:
        project = db.execute(select(Project).where(Project.id == uuid.UUID(project_id))).scalar_one()
        project.status = ProjectStatus.EXPORTING
        db.commit()

        try:
            segments = db.execute(
                select(Segment)
                .where(Segment.project_id == uuid.UUID(project_id), Segment.included == True)
                .order_by(Segment.index)
            ).scalars().all()

            timeline = [
                {
                    "start": s.start_adjusted if s.start_adjusted is not None else s.start,
                    "end": s.end_adjusted if s.end_adjusted is not None else s.end,
                }
                for s in segments
            ]

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = str(Path(tmpdir) / "highlights.mp4")
                run_engine_export(video_local_path, timeline, output_path)

                project.status = ProjectStatus.READY
                db.commit()

                return {"output_key": upload_callback_key}
        except Exception as e:
            project.status = ProjectStatus.FAILED
            project.error_message = str(e)[:1024]
            db.commit()
            raise
