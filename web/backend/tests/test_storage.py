"""Unit tests for S3ObjectStorage's crash-resilience around completing a
multipart upload.

These exercise ``S3ObjectStorage`` directly (with a stubbed boto3 client)
rather than through the FastAPI app, because the scenario under test is a
storage-layer implementation detail: the process can crash after S3 accepts
`CompleteMultipartUpload` but before our own DB commit lands, so a retried
`complete_multipart_upload` call must recognize S3's resulting
`NoSuchUpload` error as "already done" rather than a real failure -- but
only when the object actually exists.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from app.config import Settings
from app.services.storage import ObjectMetadata, S3ObjectStorage, UploadPart


def _client_error(code: str) -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": "stub"}},
        operation_name="CompleteMultipartUpload",
    )


class _StubClient:
    def __init__(self, *, complete_error: ClientError, head_result: ObjectMetadata | ClientError):
        self._complete_error = complete_error
        self._head_result = head_result
        self.complete_calls = 0
        self.head_calls = 0

    def complete_multipart_upload(self, **kwargs):
        self.complete_calls += 1
        raise self._complete_error

    def head_object(self, **kwargs):
        self.head_calls += 1
        if isinstance(self._head_result, ClientError):
            raise self._head_result
        return {
            "ContentLength": self._head_result.size_bytes,
            "ContentType": self._head_result.content_type,
        }


@pytest.fixture
def storage() -> S3ObjectStorage:
    return S3ObjectStorage(Settings())


def test_complete_multipart_upload_treats_no_such_upload_as_idempotent_when_object_exists(
    storage: S3ObjectStorage,
) -> None:
    stub = _StubClient(
        complete_error=_client_error("NoSuchUpload"),
        head_result=ObjectMetadata(size_bytes=123, content_type="video/mp4"),
    )
    storage._client = stub

    # Must not raise: an earlier attempt already completed this upload.
    storage.complete_multipart_upload(
        object_key="projects/x/source/y.mp4",
        upload_id="upload-1",
        parts=[UploadPart(part_number=1, etag="etag-1")],
    )
    assert stub.complete_calls == 1
    assert stub.head_calls == 1


def test_complete_multipart_upload_reraises_no_such_upload_when_object_missing(
    storage: S3ObjectStorage,
) -> None:
    stub = _StubClient(
        complete_error=_client_error("NoSuchUpload"),
        head_result=_client_error("NoSuchKey"),
    )
    storage._client = stub

    with pytest.raises(ClientError) as excinfo:
        storage.complete_multipart_upload(
            object_key="projects/x/source/y.mp4",
            upload_id="upload-1",
            parts=[UploadPart(part_number=1, etag="etag-1")],
        )
    # The original NoSuchUpload error is what propagates, not NoSuchKey.
    assert excinfo.value.response["Error"]["Code"] == "NoSuchUpload"
    assert stub.head_calls == 1


def test_complete_multipart_upload_reraises_other_client_errors_without_checking_object(
    storage: S3ObjectStorage,
) -> None:
    stub = _StubClient(
        complete_error=_client_error("InvalidPart"),
        head_result=ObjectMetadata(size_bytes=123, content_type="video/mp4"),
    )
    storage._client = stub

    with pytest.raises(ClientError) as excinfo:
        storage.complete_multipart_upload(
            object_key="projects/x/source/y.mp4",
            upload_id="upload-1",
            parts=[UploadPart(part_number=1, etag="etag-1")],
        )
    assert excinfo.value.response["Error"]["Code"] == "InvalidPart"
    # A non-NoSuchUpload error is not ambiguous with the crash-recovery
    # scenario, so head_object is never consulted.
    assert stub.head_calls == 0
