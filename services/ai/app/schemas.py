from __future__ import annotations

import base64
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .config import settings

_ALLOWED_IMAGE_PREFIXES = (
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/webp;base64,",
)


class InsightRequest(BaseModel):
    project_id: str
    prompt_version: str = "2026-11-01"
    evidence: dict[str, Any] = Field(default_factory=dict)
    images: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_images(self) -> "InsightRequest":
        """Reject anything that is not a capped image data URI.

        This is the hard boundary that keeps raw IQ (or arbitrary files) from
        ever reaching the model, even if a caller is buggy or hostile.
        """

        total = 0
        for name, data_uri in self.images.items():
            if not isinstance(data_uri, str) or not data_uri.startswith(
                _ALLOWED_IMAGE_PREFIXES
            ):
                raise ValueError(f"image {name!r} is not an image data URI")
            # Check the encoded size before decoding so a huge body cannot
            # force a large allocation in the sidecar.
            if len(data_uri) > settings.AI_MAX_IMAGE_BYTES * 2:
                raise ValueError(
                    f"image {name!r} exceeds {settings.AI_MAX_IMAGE_BYTES} byte cap"
                )
            try:
                raw = base64.b64decode(data_uri.split(",", 1)[1], validate=True)
            except (ValueError, IndexError) as exc:
                raise ValueError(f"image {name!r} has invalid base64 data") from exc
            if len(raw) > settings.AI_MAX_IMAGE_BYTES:
                raise ValueError(
                    f"image {name!r} exceeds {settings.AI_MAX_IMAGE_BYTES} byte cap"
                )
            total += len(raw)
        if total > settings.AI_MAX_TOTAL_IMAGE_BYTES:
            raise ValueError(
                f"image bundle exceeds {settings.AI_MAX_TOTAL_IMAGE_BYTES} byte cap"
            )
        return self


class InsightHypothesis(BaseModel):
    label: str = "unknown"
    agreement_with_dsp: bool | None = None
    confidence_note: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class InsightConflict(BaseModel):
    between: list[str] = Field(default_factory=list)
    explanation: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class InsightAnomaly(BaseModel):
    description: str = ""
    severity: str = "low"
    evidence_refs: list[str] = Field(default_factory=list)


class InsightAction(BaseModel):
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    why: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class InsightResponse(BaseModel):
    summary_template: str
    summary: str = ""
    hypothesis: InsightHypothesis = Field(default_factory=InsightHypothesis)
    conflicts: list[InsightConflict] = Field(default_factory=list)
    anomalies: list[InsightAnomaly] = Field(default_factory=list)
    recommended_actions: list[InsightAction] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    citations: dict[str, str] = Field(default_factory=dict)
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)
    model_name: str = ""
    prompt_version: str = ""
