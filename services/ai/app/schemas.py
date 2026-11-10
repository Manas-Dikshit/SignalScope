from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InsightRequest(BaseModel):
    project_id: str
    prompt_version: str = "2026-11-01"
    evidence: dict[str, Any] = Field(default_factory=dict)
    images: dict[str, str] = Field(default_factory=dict)


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
