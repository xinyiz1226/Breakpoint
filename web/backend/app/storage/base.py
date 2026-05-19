from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def generate_upload_key(self, user_id: str, filename: str) -> str:
        ...

    @abstractmethod
    async def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str:
        ...

    @abstractmethod
    async def generate_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        ...

    @abstractmethod
    async def upload(self, key: str, data: bytes) -> None:
        ...

    @abstractmethod
    async def download(self, key: str) -> bytes:
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        ...
