"""Focused coverage for env-configurable upload/duration settings."""

from __future__ import annotations

import pytest

from app.config import Settings


def test_defaults_match_documented_layer_1_caps() -> None:
    settings = Settings(_env_file=None)  # ignore any local .env during this check

    assert settings.max_upload_size_bytes == 20 * 1024 * 1024 * 1024  # 20 GiB
    assert settings.max_video_duration_seconds == 3 * 60 * 60  # 10800s / 3 hours
    assert settings.upload_part_presigned_url_ttl_seconds == 24 * 60 * 60
    assert settings.presigned_url_ttl_seconds == 60 * 60


def test_upload_and_duration_caps_are_env_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BREAKPOINT_MAX_UPLOAD_SIZE_BYTES", str(5 * 1024 * 1024 * 1024))
    monkeypatch.setenv("BREAKPOINT_MAX_VIDEO_DURATION_SECONDS", "7200")

    settings = Settings(_env_file=None)

    assert settings.max_upload_size_bytes == 5 * 1024 * 1024 * 1024
    assert settings.max_video_duration_seconds == 7200


def test_browser_storage_endpoint_is_independently_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BREAKPOINT_S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv(
        "BREAKPOINT_S3_BROWSER_ENDPOINT_URL", "http://localhost:9000"
    )

    settings = Settings(_env_file=None)

    assert settings.s3_endpoint_url == "http://minio:9000"
    assert settings.s3_browser_endpoint_url == "http://localhost:9000"


def test_upload_part_ttl_is_independently_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BREAKPOINT_PRESIGNED_URL_TTL_SECONDS", "900")
    monkeypatch.setenv("BREAKPOINT_UPLOAD_PART_PRESIGNED_URL_TTL_SECONDS", "86400")

    settings = Settings(_env_file=None)

    assert settings.presigned_url_ttl_seconds == 900
    assert settings.upload_part_presigned_url_ttl_seconds == 86400
