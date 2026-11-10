from __future__ import annotations

import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://signalscope:signalscope@localhost:5432/signalscope"
    DATABASE_URL_SYNC: str = "postgresql://signalscope:signalscope@localhost:5432/signalscope"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    DATA_DIR: str = "./data"
    MAX_UPLOAD_BYTES: int = 200 * 1024 * 1024  # 200 MB
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = "http://localhost:3000"

    # Optional local Gemma 4 sidecar. Disabled by default so the deterministic
    # DSP/API stack runs exactly as before.
    AI_ENABLED: bool = False
    AI_SERVICE_URL: str = "http://ai:8100"
    AI_MODEL: str = "google/gemma-4-E4B-it"
    AI_TIMEOUT_SECONDS: float = 120.0
    AI_PROMPT_VERSION: str = "2026-11-01"

    # Shared secret for the private AI -> DSP tool route. Empty disables the
    # route, so an accidentally exposed API cannot run analysis for anyone.
    INTERNAL_API_TOKEN: str = ""

    # Phase 3 multimodal evidence. Rendered PNGs only; raw IQ never leaves the
    # API/worker container. Caps are enforced per image and across the bundle.
    AI_EVIDENCE_IMAGES_ENABLED: bool = True
    AI_MAX_IMAGE_BYTES: int = 300_000
    AI_MAX_TOTAL_IMAGE_BYTES: int = 1_000_000

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