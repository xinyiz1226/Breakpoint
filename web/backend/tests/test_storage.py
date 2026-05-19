import pytest
from app.storage.local import LocalStorage


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(base_path=str(tmp_path))


@pytest.mark.asyncio
async def test_generate_upload_key(storage):
    key = storage.generate_upload_key("user123", "match.mp4")
    assert "user123" in key
    assert key.endswith(".mp4")


@pytest.mark.asyncio
async def test_upload_and_download(storage):
    key = storage.generate_upload_key("user1", "test.txt")
    await storage.upload(key, b"hello world")
    data = await storage.download(key)
    assert data == b"hello world"


@pytest.mark.asyncio
async def test_delete(storage):
    key = storage.generate_upload_key("user1", "del.txt")
    await storage.upload(key, b"data")
    await storage.delete(key)
    with pytest.raises(FileNotFoundError):
        await storage.download(key)


@pytest.mark.asyncio
async def test_presigned_url(storage):
    key = storage.generate_upload_key("user1", "file.mp4")
    url = await storage.generate_presigned_upload_url(key)
    assert key in url


@pytest.mark.asyncio
async def test_presigned_download_url(storage):
    key = storage.generate_upload_key("user1", "file.mp4")
    await storage.upload(key, b"data")
    url = await storage.generate_presigned_download_url(key)
    assert key in url
