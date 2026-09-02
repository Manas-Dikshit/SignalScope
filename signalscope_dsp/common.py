"""Shared types used across every DSP stage.

The single most important design rule in this codebase (per the project spec):
measured values, user-supplied values, and inferred/hypothesis values must
never be conflated. Use `Estimate` for every number that isn't a guaranteed
fact, and set `source` honestly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import numpy as np


class Source(str, Enum):
    METADATA = "metadata"          # came from a file header / SigMF sidecar
    USER_SUPPLIED = "user_supplied"  # the user typed it in
    MEASURED = "measured"          # deterministically computed from data (e.g. duration = n_samples / fs)
    ESTIMATED = "estimated"        # inferred with a specific algorithm, has uncertainty
    HYPOTHESIS = "hypothesis"      # one of several competing candidate explanations
    UNKNOWN = "unknown"            # not available and not estimated


@dataclass
class Estimate:
    """A single reported value with full provenance."""

    name: str
    value: Any
    unit: Optional[str] = None
    source: Source = Source.UNKNOWN
    confidence: Optional[float] = None  # 0..1, None if source is METADATA/USER_SUPPLIED/MEASURED (exact)
    evidence: list[str] = field(default_factory=list)
    alternatives: list["Estimate"] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def is_exact(self) -> bool:
        return self.source in (Source.METADATA, Source.USER_SUPPLIED, Source.MEASURED)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "source": self.source.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "warnings": self.warnings,
        }


@dataclass
class RecordingMetadata:
    sample_rate: Estimate            # Hz
    center_frequency: Optional[Estimate]  # Hz, may be None/unknown
    is_complex: bool
    channel_count: int
    sample_dtype: str
    duration_seconds: Optional[float] = None
    total_samples: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class Recording:
    """Normalized in-memory representation. All downstream stages consume this."""

    samples: np.ndarray  # complex64, shape (N,)
    metadata: RecordingMetadata
    source_path: str

    def duration_s(self) -> float:
        fs = self.metadata.sample_rate.value
        if not fs:
            return float("nan")
        return len(self.samples) / fs
