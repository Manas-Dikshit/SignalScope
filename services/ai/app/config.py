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
    # none | 4bit | 8bit. 4bit needs the optional bitsandbytes dependency and
    # is what makes E2B/E4B fit on consumer GPUs (8 GB or less).
    AI_QUANTIZATION: str = "none"
    # Optional cap for the accelerator, e.g. "5GiB". Empty means let
    # accelerate decide. Remaining layers spill to CPU when capped.
    AI_MAX_GPU_MEMORY: str = ""
    AI_ENABLE_THINKING: bool = False
    AI_MAX_NEW_TOKENS: int = 1024
    AI_PROMPT_VERSION: str = "2026-11-01"
    AI_MAX_TOOL_STEPS: int = 6

    # Private API route that executes allowlisted DSP tools. The AI service never
    # touches the database or recording volume directly.
    API_INTERNAL_URL: str = "http://api:8000"
    INTERNAL_API_TOKEN: str = ""
    AI_TOOL_TIMEOUT_SECONDS: float = 30.0

    # Multimodal evidence arrives as base64 PNG data URIs. The sidecar refuses
    # anything that is not an image or that exceeds these caps.
    AI_MAX_IMAGE_BYTES: int = 300_000
    AI_MAX_TOTAL_IMAGE_BYTES: int = 1_000_000


settings = AISettings()
