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
    def __init__(
        self, *, complete_error: ClientError | None = None, abort_error: ClientError | None = None
    ) -> None:
        self._complete_error = complete_error
        self._abort_error = abort_error
        self.complete_calls = 0
        self.delete_calls: list[tuple[str, str]] = []
        self.abort_calls: list[tuple[str, str, str]] = []
        self.presigned_url_calls: list[dict] = []

    def complete_multipart_upload(self, **kwargs):
        self.complete_calls += 1
        if self._complete_error is not None:
            raise self._complete_error

    def delete_object(self, *, Bucket: str, Key: str):
        self.delete_calls.append((Bucket, Key))

    def abort_multipart_upload(self, *, Bucket: str, Key: str, UploadId: str):
        self.abort_calls.append((Bucket, Key, UploadId))
        if self._abort_error is not None:
            raise self._abort_error

    def generate_presigned_url(self, ClientMethod: str, Params: dict, ExpiresIn: int):
        self.presigned_url_calls.append({"ClientMethod": ClientMethod, "Params": dict(Params), "ExpiresIn": ExpiresIn})
        return f"https://stub.test/{Params['Key']}?part={Params['PartNumber']}"


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


def test_generate_presigned_part_urls_binds_content_length_per_part(storage: S3ObjectStorage) -> None:
    """Each presigned ``upload_part`` URL must sign a ``ContentLength``
    ``Params`` entry, binding the client's Content-Length header to exactly
    the length this part is allowed to be -- otherwise a browser could
    upload a wildly different-sized part than the one the size/part_count
    contract validated against.
    """
    stub = _StubClient()
    storage._client = stub
    storage._presign_client = stub

    part_lengths = [5 * 1024 * 1024, 3 * 1024 * 1024]
    urls = storage.generate_presigned_part_urls(
        object_key="projects/x/source/y.mp4",
        upload_id="upload-1",
        part_lengths=part_lengths,
        expires_in_seconds=3600,
    )

    assert [entry[0] for entry in urls] == [1, 2]
    assert [entry[2] for entry in urls] == part_lengths
    assert len(stub.presigned_url_calls) == 2
    for call, expected_length, expected_part_number in zip(
        stub.presigned_url_calls, part_lengths, [1, 2]
    ):
        assert call["Params"]["ContentLength"] == expected_length
        assert call["Params"]["PartNumber"] == expected_part_number
        assert call["Params"]["UploadId"] == "upload-1"


# --- Independent review round 2 item 1: narrow abort_multipart_upload idempotency --


def test_abort_multipart_upload_swallows_no_such_upload(storage: S3ObjectStorage) -> None:
    """A retried abort against a multipart upload that is already gone
    (e.g. a stale-recovery sweep reclaiming a task whose earlier attempt
    actually succeeded in storage before crashing) must be treated as
    success, not as a failure -- the desired end state (no such upload)
    already holds."""
    stub = _StubClient(abort_error=_client_error("NoSuchUpload"))
    storage._client = stub

    storage.abort_multipart_upload(object_key="projects/x/source/y.mp4", upload_id="upload-1")
    assert stub.abort_calls == [(storage._bucket, "projects/x/source/y.mp4", "upload-1")]


def test_abort_multipart_upload_reraises_other_client_errors(storage: S3ObjectStorage) -> None:
    stub = _StubClient(abort_error=_client_error("AccessDenied"))
    storage._client = stub

    with pytest.raises(ClientError) as excinfo:
        storage.abort_multipart_upload(object_key="projects/x/source/y.mp4", upload_id="upload-1")
    assert excinfo.value.response["Error"]["Code"] == "AccessDenied"


def test_presigned_urls_use_browser_endpoint_without_rewriting_signatures(monkeypatch) -> None:
    clients = []

    class _EndpointClient:
        def __init__(self, endpoint_url: str) -> None:
            self.endpoint_url = endpoint_url

        def generate_presigned_url(self, method: str, Params: dict, ExpiresIn: int) -> str:
            return (
                f"{self.endpoint_url}/breakpoint-videos/{Params['Key']}"
                f"?method={method}&signature=for-{self.endpoint_url}"
            )

    def client_factory(_service: str, *, endpoint_url: str, **_kwargs):
        client = _EndpointClient(endpoint_url)
        clients.append(client)
        return client

    monkeypatch.setattr("app.services.storage.boto3.client", client_factory)
    storage = S3ObjectStorage(
        Settings(
            s3_endpoint_url="http://minio:9000",
            s3_browser_endpoint_url="http://localhost:9000",
        )
    )

    get_url = storage.generate_presigned_get_url(
        object_key="projects/x/source/y.mp4", expires_in_seconds=60
    )
    part_url = storage.generate_presigned_part_urls(
        object_key="projects/x/source/y.mp4",
        upload_id="upload-1",
        part_lengths=[8],
        expires_in_seconds=60,
    )[0][1]

    assert [client.endpoint_url for client in clients] == [
        "http://minio:9000",
        "http://localhost:9000",
    ]
    assert get_url.startswith("http://localhost:9000/")
    assert part_url.startswith("http://localhost:9000/")
    assert "signature=for-http://localhost:9000" in get_url
