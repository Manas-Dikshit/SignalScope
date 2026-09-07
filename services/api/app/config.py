from __future__ import annotations

import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://signalscope:signalscope@localhost:5432/signalscope"
    DATABASE_URL_SYNC: str = "postgresql://signalscope:signalscope@localhost:5432/signalscope"
    REDIS_URL: str = "redis://localhost:6379/0"
    DATA_DIR: str = "./data"
    MAX_UPLOAD_BYTES: int = 200 * 1024 * 1024  # 200 MB
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = "http://localhost:3000"

    # `CORS_ORIGINS` is a string env var (comma-separated or JSON array).
    # Kept as `str` so pydantic-settings doesn't force JSON decoding of
    # complex-typed env vars across versions.
    @property
    def cors_origins(self) -> list[str]:
        v = self.CORS_ORIGINS.strip()
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return [str(o) for o in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return [s.strip() for s in v.split(",") if s.strip()]


settings = Settings()