"""Unit tests for S3ObjectStorage's crash-resilience contract around
completing a multipart upload, and for object deletion.

These exercise ``S3ObjectStorage`` directly (with a stubbed boto3 client)
rather than through the FastAPI app, because the scenario under test is a
storage-layer implementation detail: the process can crash after S3 accepts
`CompleteMultipartUpload` but before our own DB commit lands, so a retried
`complete_multipart_upload` call may see S3's resulting `NoSuchUpload`
error either for a genuine failure or for that crash-recovery case. The
storage layer no longer guesses between these itself (checking object
existence internally used to make this "idempotent if the object exists",
which is unsafe -- an unrelated object could occupy the same key for a
genuinely wrong/stale upload id). It now always raises the domain
``MultipartUploadNotFound`` exception and leaves recovery to a caller with
its own durable claim to verify against (see
``app.routers.uploads.finalize_upload``).
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from app.config import Settings
from app.services.storage import MultipartUploadNotFound, S3ObjectStorage, UploadPart


def _client_error(code: str) -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": "stub"}},
        operation_name="CompleteMultipartUpload",
    )


class _StubClient:
    def __init__(self, *, complete_error: ClientError | None = None) -> None:
        self._complete_error = complete_error
        self.complete_calls = 0
        self.delete_calls: list[tuple[str, str]] = []

    def complete_multipart_upload(self, **kwargs):
        self.complete_calls += 1
        if self._complete_error is not None:
            raise self._complete_error

    def delete_object(self, *, Bucket: str, Key: str):
        self.delete_calls.append((Bucket, Key))


@pytest.fixture
def storage() -> S3ObjectStorage:
    return S3ObjectStorage(Settings())


def test_complete_multipart_upload_raises_domain_exception_on_no_such_upload(
    storage: S3ObjectStorage,
) -> None:
    stub = _StubClient(complete_error=_client_error("NoSuchUpload"))
    storage._client = stub

    with pytest.raises(MultipartUploadNotFound) as excinfo:
        storage.complete_multipart_upload(
            object_key="projects/x/source/y.mp4",
            upload_id="upload-1",
            parts=[UploadPart(part_number=1, etag="etag-1")],
        )
    assert excinfo.value.object_key == "projects/x/source/y.mp4"
    assert excinfo.value.upload_id == "upload-1"
    assert stub.complete_calls == 1


def test_complete_multipart_upload_reraises_other_client_errors(storage: S3ObjectStorage) -> None:
    stub = _StubClient(complete_error=_client_error("InvalidPart"))
    storage._client = stub

    with pytest.raises(ClientError) as excinfo:
        storage.complete_multipart_upload(
            object_key="projects/x/source/y.mp4",
            upload_id="upload-1",
            parts=[UploadPart(part_number=1, etag="etag-1")],
        )
    assert excinfo.value.response["Error"]["Code"] == "InvalidPart"


def test_complete_multipart_upload_succeeds_without_raising(storage: S3ObjectStorage) -> None:
    stub = _StubClient(complete_error=None)
    storage._client = stub

    storage.complete_multipart_upload(
        object_key="projects/x/source/y.mp4",
        upload_id="upload-1",
        parts=[UploadPart(part_number=1, etag="etag-1")],
    )
    assert stub.complete_calls == 1


def test_delete_object_calls_the_underlying_client(storage: S3ObjectStorage) -> None:
    stub = _StubClient()
    storage._client = stub

    storage.delete_object(object_key="projects/x/source/y.mp4")
    assert stub.delete_calls == [(storage._bucket, "projects/x/source/y.mp4")]
