"""S3-compatible object storage abstraction, backed by MinIO in development.

``ObjectStorage`` is a small protocol so tests can inject an in-memory fake
instead of talking to a real S3-compatible endpoint. Object keys are always
server-generated (never derived from client input) to prevent path traversal
or collisions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import Settings

_MAX_OBJECT_KEY_SUFFIX_LENGTH = 10


@dataclass(frozen=True)
class ObjectMetadata:
    size_bytes: int
    content_type: str | None


@dataclass(frozen=True)
class UploadPart:
    part_number: int
    etag: str


class ObjectStorage(Protocol):
    def generate_object_key(self, *, project_id: uuid.UUID, filename: str) -> str: ...

    def create_multipart_upload(self, *, object_key: str, content_type: str) -> str: ...

    def generate_presigned_part_urls(
        self, *, object_key: str, upload_id: str, part_count: int, expires_in_seconds: int
    ) -> list[tuple[int, str]]: ...

    def complete_multipart_upload(
        self, *, object_key: str, upload_id: str, parts: list[UploadPart]
    ) -> None: ...

    def abort_multipart_upload(self, *, object_key: str, upload_id: str) -> None: ...

    def head_object(self, *, object_key: str) -> ObjectMetadata: ...

    def generate_presigned_get_url(self, *, object_key: str, expires_in_seconds: int) -> str: ...

    def check_connection(self) -> bool: ...


class S3ObjectStorage:
    """Boto3-backed implementation targeting any S3-compatible endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bucket = settings.s3_bucket
        addressing_style = "path" if settings.s3_use_path_style else "auto"
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": addressing_style}),
        )

    def generate_object_key(self, *, project_id: uuid.UUID, filename: str) -> str:
        suffix = PurePosixPath(filename).suffix.lower()
        if len(suffix) > _MAX_OBJECT_KEY_SUFFIX_LENGTH:
            suffix = ""
        return f"projects/{project_id}/source/{uuid.uuid4()}{suffix}"

    def create_multipart_upload(self, *, object_key: str, content_type: str) -> str:
        response = self._client.create_multipart_upload(
            Bucket=self._bucket, Key=object_key, ContentType=content_type
        )
        return response["UploadId"]

    def generate_presigned_part_urls(
        self, *, object_key: str, upload_id: str, part_count: int, expires_in_seconds: int
    ) -> list[tuple[int, str]]:
        urls: list[tuple[int, str]] = []
        for part_number in range(1, part_count + 1):
            url = self._client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=expires_in_seconds,
            )
            urls.append((part_number, url))
        return urls

    def complete_multipart_upload(
        self, *, object_key: str, upload_id: str, parts: list[UploadPart]
    ) -> None:
        ordered_parts = sorted(parts, key=lambda part: part.part_number)
        try:
            self._client.complete_multipart_upload(
                Bucket=self._bucket,
                Key=object_key,
                UploadId=upload_id,
                MultipartUpload={
                    "Parts": [
                        {"PartNumber": part.part_number, "ETag": part.etag}
                        for part in ordered_parts
                    ]
                },
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code != "NoSuchUpload":
                raise
            # S3 also returns NoSuchUpload when this exact multipart upload
            # was already completed by an earlier attempt that crashed (or
            # was retried) after S3 accepted the completion but before our
            # own DB commit landed. Treat that as an idempotent no-op, but
            # only if the object genuinely exists — otherwise the upload id
            # is unknown/aborted for a real reason and the error stands.
            try:
                self.head_object(object_key=object_key)
            except ClientError:
                raise exc from None

    def abort_multipart_upload(self, *, object_key: str, upload_id: str) -> None:
        self._client.abort_multipart_upload(Bucket=self._bucket, Key=object_key, UploadId=upload_id)

    def head_object(self, *, object_key: str) -> ObjectMetadata:
        response = self._client.head_object(Bucket=self._bucket, Key=object_key)
        return ObjectMetadata(
            size_bytes=response["ContentLength"], content_type=response.get("ContentType")
        )

    def generate_presigned_get_url(self, *, object_key: str, expires_in_seconds: int) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_key},
            ExpiresIn=expires_in_seconds,
        )

    def check_connection(self) -> bool:
        self._client.head_bucket(Bucket=self._bucket)
        return True
