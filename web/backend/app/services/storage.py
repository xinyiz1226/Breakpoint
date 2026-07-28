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


class ObjectNotFound(Exception):
    """Raised when the storage backend reports an object key as genuinely
    missing (S3: ``head_object`` 404/``NoSuchKey``).

    Unlike ``MultipartUploadNotFound``, this is unambiguous: the caller
    asked the storage backend directly whether the object exists, and it
    does not. A caller recovering from ``MultipartUploadNotFound`` uses
    this to distinguish "the completion was ambiguous but the object is
    actually there" from "there is genuinely nothing to recover."
    """

    def __init__(self, *, object_key: str) -> None:
        super().__init__(f"Object {object_key!r} was not found")
        self.object_key = object_key


class MultipartUploadNotFound(Exception):
    """Raised when the storage backend reports the multipart upload id as
    unknown (S3: ``NoSuchUpload``) during ``complete_multipart_upload``.

    This is deliberately ambiguous: it can mean either "the upload id is
    genuinely unknown/aborted" or "an earlier attempt already completed this
    exact multipart upload, and the process crashed after S3 accepted the
    completion but before our own DB commit landed." The storage layer no
    longer guesses between these by checking object existence itself --
    only a caller that has independently persisted a durable claim (e.g. a
    ``VideoAsset`` already committed as ``FINALIZING`` for this exact
    idempotency key + request fingerprint) may attempt recovery, by calling
    ``head_object`` itself to verify the object.
    """

    def __init__(self, *, object_key: str, upload_id: str) -> None:
        super().__init__(f"Multipart upload {upload_id!r} for object {object_key!r} was not found")
        self.object_key = object_key
        self.upload_id = upload_id


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

    def delete_object(self, *, object_key: str) -> None: ...

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
            # Ambiguous by construction -- see MultipartUploadNotFound's
            # docstring. The storage layer no longer resolves this itself;
            # it is the caller's job to decide, using its own durable state,
            # whether recovery via head_object is appropriate.
            raise MultipartUploadNotFound(object_key=object_key, upload_id=upload_id) from exc

    def abort_multipart_upload(self, *, object_key: str, upload_id: str) -> None:
        self._client.abort_multipart_upload(Bucket=self._bucket, Key=object_key, UploadId=upload_id)

    def delete_object(self, *, object_key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=object_key)

    def head_object(self, *, object_key: str) -> ObjectMetadata:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=object_key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code not in ("404", "NoSuchKey"):
                raise
            raise ObjectNotFound(object_key=object_key) from exc
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
