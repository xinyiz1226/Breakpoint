"""In-memory fakes for the email and object-storage protocols, used to keep
tests hermetic (no real SMTP server or S3-compatible endpoint required).
"""

from __future__ import annotations

import re
import smtplib
import uuid
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from botocore.exceptions import ClientError

from app.services.storage import MultipartUploadNotFound, ObjectMetadata, ObjectNotFound

_URL_PATTERN = re.compile(r"(https?://\S+)")


@dataclass
class SentEmail:
    to_address: str
    subject: str
    body: str

    @property
    def first_url(self) -> str:
        match = _URL_PATTERN.search(self.body)
        assert match is not None, f"no URL found in email body: {self.body!r}"
        return match.group(1)

    @property
    def token(self) -> str:
        url = self.first_url
        _, _, query = url.partition("?token=")
        assert query, f"no token query param found in URL: {url!r}"
        return query


class FakeEmailSender:
    """Records sent emails; can simulate transient SMTP failures.

    ``fail_next_sends`` lets a test simulate an SMTP server being briefly
    unavailable: the next N calls to ``send`` raise instead of recording an
    email, then delivery resumes as normal.
    """

    def __init__(self) -> None:
        self.sent_emails: list[SentEmail] = []
        self.fail_next_sends: int = 0

    def send(self, *, to_address: str, subject: str, body: str) -> None:
        if self.fail_next_sends > 0:
            self.fail_next_sends -= 1
            raise smtplib.SMTPServerDisconnected("simulated SMTP failure")
        self.sent_emails.append(SentEmail(to_address=to_address, subject=subject, body=body))

    @property
    def last_email(self) -> SentEmail:
        assert self.sent_emails, "no email was sent"
        return self.sent_emails[-1]


@dataclass
class _FakeUpload:
    object_key: str
    content_type: str


class FakeObjectStorage:
    """Simulates an S3-compatible endpoint entirely in memory.

    Tests can pre-populate ``objects`` to simulate the state a real
    multipart upload would have left behind before calling finalize.
    ``fail_next_deletes``/``fail_next_aborts`` let a test inject a
    transient storage-side failure for the next N ``delete_object``/
    ``abort_multipart_upload`` calls, to exercise durable
    failed/pending-retry cleanup-task handling.
    """

    def __init__(self) -> None:
        self.uploads: dict[str, _FakeUpload] = {}
        self.completed_upload_ids: set[str] = set()
        self.aborted_upload_ids: set[str] = set()
        self.deleted_object_keys: list[str] = []
        self.objects: dict[str, ObjectMetadata] = {}
        self.connection_ok: bool = True
        self.fail_next_deletes: int = 0
        self.fail_next_aborts: int = 0

    def generate_object_key(self, *, project_id: uuid.UUID, filename: str) -> str:
        suffix = PurePosixPath(filename).suffix.lower()
        return f"projects/{project_id}/source/{uuid.uuid4()}{suffix}"

    def create_multipart_upload(self, *, object_key: str, content_type: str) -> str:
        upload_id = uuid.uuid4().hex
        self.uploads[upload_id] = _FakeUpload(object_key=object_key, content_type=content_type)
        return upload_id

    def generate_presigned_part_urls(
        self, *, object_key: str, upload_id: str, part_count: int, expires_in_seconds: int
    ) -> list[tuple[int, str]]:
        return [
            (n, f"https://fake-s3.test/{object_key}?part={n}&uploadId={upload_id}")
            for n in range(1, part_count + 1)
        ]

    def complete_multipart_upload(self, *, object_key: str, upload_id: str, parts) -> None:
        upload = self.uploads.get(upload_id)
        if upload is None or upload.object_key != object_key or upload_id in self.completed_upload_ids:
            raise MultipartUploadNotFound(object_key=object_key, upload_id=upload_id)
        self.completed_upload_ids.add(upload_id)
        self.objects.setdefault(
            object_key, ObjectMetadata(size_bytes=0, content_type=upload.content_type)
        )

    def abort_multipart_upload(self, *, object_key: str, upload_id: str) -> None:
        if self.fail_next_aborts > 0:
            self.fail_next_aborts -= 1
            raise ClientError(
                {"Error": {"Code": "InternalError", "Message": "simulated abort failure"}},
                "AbortMultipartUpload",
            )
        self.aborted_upload_ids.add(upload_id)

    def delete_object(self, *, object_key: str) -> None:
        if self.fail_next_deletes > 0:
            self.fail_next_deletes -= 1
            raise ClientError(
                {"Error": {"Code": "InternalError", "Message": "simulated delete failure"}},
                "DeleteObject",
            )
        self.objects.pop(object_key, None)
        self.deleted_object_keys.append(object_key)

    def head_object(self, *, object_key: str) -> ObjectMetadata:
        metadata = self.objects.get(object_key)
        if metadata is None:
            raise ObjectNotFound(object_key=object_key)
        return metadata

    def generate_presigned_get_url(self, *, object_key: str, expires_in_seconds: int) -> str:
        return f"https://fake-s3.test/{object_key}?signed=1&ttl={expires_in_seconds}"

    def check_connection(self) -> bool:
        if not self.connection_ok:
            raise ClientError(
                {"Error": {"Code": "503", "Message": "Service unavailable"}}, "HeadBucket"
            )
        return True
