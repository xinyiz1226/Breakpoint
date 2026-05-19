import tempfile
import uuid

from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.models.project import Project, Segment, ProjectStatus
from app.services.analysis_service import run_engine_analysis
from app.tasks.celery_app import celery_app


def _get_sync_engine():
    url = settings.database_url
    url = url.replace("+asyncpg", "").replace("+aiosqlite", "")
    return create_engine(url, echo=False)


@celery_app.task(bind=True)
def analyze_video(self, project_id: str, video_local_path: str):
    engine = _get_sync_engine()
    with Session(engine) as db:
        project = db.execute(select(Project).where(Project.id == uuid.UUID(project_id))).scalar_one()
        project.status = ProjectStatus.ANALYZING
        project.celery_task_id = self.request.id
        db.commit()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                report = run_engine_analysis(video_local_path, tmpdir)

                for item in report:
                    segment = Segment(
                        project_id=uuid.UUID(project_id),
                        index=item["index"],
                        start=item["start"],
                        end=item["end"],
                        score=item.get("score", 0),
                        features=item.get("features", {}),
                        included=item.get("score", 0) > 1.7,
                    )
                    db.add(segment)

                project.status = ProjectStatus.READY
                db.commit()
        except Exception as e:
            project.status = ProjectStatus.FAILED
            project.error_message = str(e)[:1024]
            db.commit()
            raise
