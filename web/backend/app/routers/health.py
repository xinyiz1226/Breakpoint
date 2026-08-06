"""Liveness/readiness endpoints.

Readiness always checks the database. It only checks object storage if a
storage client is configured, and only treats storage-specific errors
(``BotoCoreError``/``ClientError``) as a readiness failure rather than a
broad exception catch.
"""

from __future__ import annotations

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_storage
from app.services.storage import ObjectStorage

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(
    response: Response,
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
) -> dict[str, object]:
    checks: dict[str, str] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError:
        checks["database"] = "unavailable"

    try:
        storage.check_connection()
        checks["storage"] = "ok"
    except (BotoCoreError, ClientError):
        checks["storage"] = "unavailable"

    is_ready = all(value == "ok" for value in checks.values())
    response.status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if is_ready else "unavailable", "checks": checks}
