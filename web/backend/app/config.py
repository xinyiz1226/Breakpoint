"""Application configuration loaded from environment variables.

All settings are configurable via environment variables prefixed with
``BREAKPOINT_`` (see ``model_config`` below). Tests override individual
values via ``get_settings.cache_clear()`` plus environment variables, or by
constructing a ``Settings`` instance directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GIGABYTE = 1024 * 1024 * 1024
DEFAULT_MONTHLY_ANALYSIS_SECONDS = 10 * 60 * 60  # 10 hours
DEFAULT_MAX_UPLOAD_SIZE_BYTES = 20 * GIGABYTE  # 20 GiB
DEFAULT_MAX_VIDEO_DURATION_SECONDS = 3 * 60 * 60  # 3 hours
DEFAULT_STORAGE_BYTES = 50 * GIGABYTE  # 50 GiB


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BREAKPOINT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"

    # Database
    database_url: str = "postgresql+psycopg2://breakpoint:breakpoint@localhost:5432/breakpoint"

    # Auth / JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    refresh_cookie_name: str = "bp_refresh_token"
    refresh_cookie_secure: bool = True
    email_verification_ttl_hours: int = 24
    password_reset_ttl_hours: int = 1

    # CORS
    cors_allow_origins: list[str] = []

    # Email / SMTP (Mailpit in local compose)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_use_tls: bool = False
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_address: str = "no-reply@breakpoint.local"
    app_base_url: str = "http://localhost:3000"

    # Object storage (MinIO / S3-compatible)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "breakpoint-videos"
    s3_region: str = "us-east-1"
    s3_use_path_style: bool = True
    presigned_url_ttl_seconds: int = 3600

    # Uploads. Declared size/duration are validated by this layer at
    # initiate time; actual size is re-validated at finalize. Duration is
    # still authoritatively re-checked later by a future worker (ffprobe)
    # against the same cap: this layer only validates and reserves quota
    # against the client's *declared* duration, never a probed one (see
    # VideoAsset.declared_duration_seconds vs. duration_seconds/duration_status).
    max_upload_size_bytes: int = DEFAULT_MAX_UPLOAD_SIZE_BYTES
    max_video_duration_seconds: int = DEFAULT_MAX_VIDEO_DURATION_SECONDS
    multipart_min_part_size_bytes: int = 8 * 1024 * 1024  # S3 minimum is 5 MiB
    # How long a multipart upload's presigned part URLs/upload_id remain
    # valid before the durable expiry-sweep contract (see
    # app.services.storage_cleanup.run_due_storage_cleanup_sweep) is allowed
    # to abort it and release its reservations.
    multipart_upload_ttl_hours: int = 24
    asset_retention_days: int = 7

    # Quota defaults (per-user overrides live in the users table)
    default_monthly_analysis_seconds: int = DEFAULT_MONTHLY_ANALYSIS_SECONDS
    default_max_active_analysis_jobs: int = 1
    default_storage_bytes: int = DEFAULT_STORAGE_BYTES

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _require_or_default_jwt_secret(self) -> "Settings":
        if not self.jwt_secret_key:
            if self.environment == "production":
                raise ValueError(
                    "BREAKPOINT_JWT_SECRET_KEY must be set when BREAKPOINT_ENVIRONMENT=production"
                )
            # Clearly-labeled, non-production-only fallback so local dev and
            # tests work without extra setup.
            self.jwt_secret_key = "insecure-dev-secret-do-not-use-in-production"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
