import uuid
from pathlib import Path

from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, base_path: str | None = None):
        from app.config import settings
        self.base_path = Path(base_path or settings.local_storage_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def generate_upload_key(self, user_id: str, filename: str) -> str:
        ext = Path(filename).suffix
        return f"{user_id}/{uuid.uuid4().hex}{ext}"

    async def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str:
        return f"local://{(self.base_path / key).as_posix()}"

    async def generate_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        return f"local://{(self.base_path / key).as_posix()}"

    async def upload(self, key: str, data: bytes) -> None:
        path = self.base_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def download(self, key: str) -> bytes:
        path = self.base_path / key
        if not path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self.base_path / key
        if path.exists():
            path.unlink()
