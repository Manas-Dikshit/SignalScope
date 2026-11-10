from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseSettings):
    """Runtime configuration for the local Gemma 4 sidecar.

    The default backend is ``fake`` so the API/UI can be developed and tested
    without downloading model weights. Set ``AI_BACKEND=transformers`` for a
    real local Gemma 4 run.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    AI_BACKEND: str = "fake"  # fake | transformers
    AI_MODEL: str = "google/gemma-4-E4B-it"
    AI_DEVICE: str = "auto"
    AI_ENABLE_THINKING: bool = False
    AI_MAX_NEW_TOKENS: int = 1024
    AI_PROMPT_VERSION: str = "2026-11-01"


settings = AISettings()
