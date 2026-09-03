from __future__ import annotations

import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return [s.strip() for s in v.split(",") if s.strip()]
        return v

    DATABASE_URL: str = "postgresql+asyncpg://signalscope:signalscope@localhost:5432/signalscope"
    REDIS_URL: str = "redis://localhost:6379/0"
    DATA_DIR: str = "./data"
    MAX_UPLOAD_BYTES: int = 200 * 1024 * 1024  # 200 MB
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


settings = Settings()
