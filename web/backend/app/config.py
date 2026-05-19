from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/breakpoint"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 30

    storage_backend: str = "local"  # "local" | "oss" | "azure"

    # Aliyun OSS
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_endpoint: str = ""
    oss_bucket: str = ""

    # Azure Blob
    azure_connection_string: str = ""
    azure_container: str = ""

    # Local storage (dev)
    local_storage_path: str = "./uploads"

    # Engine
    engine_path: str = "../../engine"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
