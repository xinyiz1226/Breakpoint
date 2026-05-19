import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

from app.config import settings
from app.storage.base import StorageBackend


class AzureBlobStorage(StorageBackend):
    def __init__(self):
        self.client = BlobServiceClient.from_connection_string(settings.azure_connection_string)
        self.container = settings.azure_container

    def generate_upload_key(self, user_id: str, filename: str) -> str:
        ext = Path(filename).suffix
        return f"uploads/{user_id}/{uuid.uuid4().hex}{ext}"

    async def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str:
        sas = generate_blob_sas(
            account_name=self.client.account_name,
            container_name=self.container,
            blob_name=key,
            account_key=self.client.credential.account_key,
            permission=BlobSasPermissions(write=True, create=True),
            expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        )
        return f"{self.client.url}{self.container}/{key}?{sas}"

    async def generate_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        sas = generate_blob_sas(
            account_name=self.client.account_name,
            container_name=self.container,
            blob_name=key,
            account_key=self.client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        )
        return f"{self.client.url}{self.container}/{key}?{sas}"

    async def upload(self, key: str, data: bytes) -> None:
        blob = self.client.get_blob_client(self.container, key)
        blob.upload_blob(data, overwrite=True)

    async def download(self, key: str) -> bytes:
        blob = self.client.get_blob_client(self.container, key)
        return blob.download_blob().readall()

    async def delete(self, key: str) -> None:
        blob = self.client.get_blob_client(self.container, key)
        blob.delete_blob()
