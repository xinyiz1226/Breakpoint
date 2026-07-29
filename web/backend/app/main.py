"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, auth, health, jobs, projects, quota, uploads

# Ensure every model is registered on Base.metadata (Alembic and
# create_all-based tests both rely on this import happening on startup).
import app.models  # noqa: F401


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Breakpoint Web API", version="1.0.0")

    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(uploads.router)
    app.include_router(jobs.router)
    app.include_router(quota.router)
    app.include_router(admin.router)

    return app


app = create_app()
