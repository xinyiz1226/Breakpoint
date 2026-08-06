"""Import every model module so ``Base.metadata`` is fully populated.

Alembic's ``env.py`` imports this package (via ``app.db.Base``) before
generating migrations, and the app imports it at startup so
``Base.metadata.create_all`` (used only by tests) sees every table.
"""

from app.models.auth import EmailToken, RefreshSession
from app.models.cleanup import StorageCleanupTask
from app.models.job import AnalysisJob, ExportJob
from app.models.project import Project
from app.models.quota import QuotaLedgerEntry
from app.models.rally import Rally, RallyEdit
from app.models.user import User
from app.models.video import VideoAsset

__all__ = [
    "User",
    "RefreshSession",
    "EmailToken",
    "Project",
    "VideoAsset",
    "AnalysisJob",
    "ExportJob",
    "Rally",
    "RallyEdit",
    "QuotaLedgerEntry",
    "StorageCleanupTask",
]
