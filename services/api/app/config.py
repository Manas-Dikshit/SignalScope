from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://signalscope:signalscope@localhost:5432/signalscope"
    REDIS_URL: str = "redis://localhost:6379/0"
    DATA_DIR: str = "./data"
    MAX_UPLOAD_BYTES: int = 200 * 1024 * 1024  # 200 MB
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


settings = Settings()
