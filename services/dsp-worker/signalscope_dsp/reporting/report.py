"""Analysis reporting: assemble per-stage results into one JSON-serializable report.

Every stage already returns provenance-carrying types (`Estimate`, `Burst`,
`ModulationHypothesis`, ...). This module is the single funnel that collects
them into a stable dict/JSON schema for the API layer and the UI.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..common import Estimate


def _json_safe(value: Any) -> Any:
    """Coerce numpy scalars/arrays (and nested containers) to plain JSON types."""
    if isinstance(value, Estimate):
        return value.to_dict()
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


@dataclass
class AnalysisReport:
    title: str
    source_path: str
    estimates: list[Estimate] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)  # bursts, hypotheses, plots meta, ...
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "source_path": self.source_path,
            "estimates": [e.to_dict() for e in self.estimates],
            "artifacts": _json_safe(self.artifacts),
            "warnings": list(self.warnings),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def build_report(
    title: str,
    source_path: str,
    estimates: list[Estimate] | tuple = (),
    artifacts: dict[str, Any] | None = None,
    warnings: list[str] | tuple = (),
) -> AnalysisReport:
    """Collect stage outputs into an `AnalysisReport`. `artifacts` may contain
    numpy values; they are coerced to plain types on serialization."""
    return AnalysisReport(
        title=title,
        source_path=source_path,
        estimates=list(estimates),
        artifacts=dict(artifacts or {}),
        warnings=list(warnings),
    )
