import uuid
from pathlib import Path

import oss2

from app.config import settings
from app.storage.base import StorageBackend


class OSSStorage(StorageBackend):
    def __init__(self):
        auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        self.bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)

    def generate_upload_key(self, user_id: str, filename: str) -> str:
        ext = Path(filename).suffix
        return f"uploads/{user_id}/{uuid.uuid4().hex}{ext}"

    async def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str:
        return self.bucket.sign_url("PUT", key, expires_in)

    async def generate_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        return self.bucket.sign_url("GET", key, expires_in)

    async def upload(self, key: str, data: bytes) -> None:
        self.bucket.put_object(key, data)

    async def download(self, key: str) -> bytes:
        result = self.bucket.get_object(key)
        return result.read()

    async def delete(self, key: str) -> None:
        self.bucket.delete_object(key)
