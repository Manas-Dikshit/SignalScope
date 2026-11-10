"""Deterministic spectral fingerprint for nearest-neighbour signal search.

The fingerprint is deliberately simple and explainable: a shape-normalised PSD
embedding plus a handful of scalar spectral features. There is no learned model,
no random seed, and no dependence on absolute amplitude or sample rate, so two
recordings of the same emitter land close together while a wideband burst, a
different modulation, or pure noise lands far away.

Everything here is an ESTIMATE. A short distance means "similar evidence", not
"same transmitter".
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..features import compute_psd, extract_spectral_features

FINGERPRINT_VERSION = "1"
EMBEDDING_BINS = 16
EMBEDDING_WEIGHT = 0.7
FEATURE_WEIGHT = 0.3

# Cosine distance above which a neighbour is considered "different". This is a
# heuristic, surfaced in the API/UI as a threshold rather than a certainty.
DEFAULT_RARE_DISTANCE_THRESHOLD = 0.35

_SCALAR_NAMES = (
    "occupied_bandwidth_ratio",
    "spectral_flatness",
    "crest_factor_norm",
    "zero_crossing_rate",
    "snr_norm",
    "drift_ratio",
)


@dataclass(frozen=True)
class SignalFingerprint:
    """A comparable, versioned representation of one recording's spectrum."""

    version: str
    dimensions: int
    vector: list[float]
    embedding: list[float]
    features: dict[str, float | None]
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "dimensions": self.dimensions,
            "vector": self.vector,
            "embedding": self.embedding,
            "features": self.features,
            "evidence": self.evidence,
            "warnings": self.warnings,
        }


def _clamp01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _unit_vector(values: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(values))
    if norm <= 1e-12:
        return np.zeros_like(values, dtype=float)
    return values.astype(float) / norm


def _psd_shape_embedding(samples: np.ndarray, sample_rate: float) -> tuple[list[float], float]:
    """Resample the PSD onto a fixed normalised-frequency grid.

    The x-axis is ``frequency / sample_rate`` so the embedding does not depend on
    the acquisition bandwidth. The y-axis is min-max normalised so it does not
    depend on absolute power or gain.
    """

    freqs, psd_db = compute_psd(samples, sample_rate, fft_size=min(1024, max(8, len(samples))))
    freq_norm = np.asarray(freqs, dtype=float) / float(sample_rate)

    grid = np.linspace(-0.5, 0.5, EMBEDDING_BINS, endpoint=False)
    resampled = np.interp(grid, freq_norm, np.asarray(psd_db, dtype=float))

    spread = float(np.max(resampled) - np.min(resampled))
    if spread <= 1e-9:
        return [0.0] * EMBEDDING_BINS, spread
    embedding = 2.0 * (resampled - np.min(resampled)) / spread - 1.0
    return embedding.astype(float).tolist(), spread


def compute_fingerprint(
    samples: np.ndarray,
    sample_rate: float,
    *,
    max_samples: int = 200_000,
) -> SignalFingerprint:
    """Compute a deterministic fingerprint over a bounded window.

    ``samples`` should already be conditioned (DC removed, normalised), matching
    what the rest of the DSP pipeline publishes as estimates.
    """

    warnings: list[str] = []
    work = np.asarray(samples)
    if work.size > max_samples:
        work = work[:max_samples]

    if work.size < 64 or not sample_rate or sample_rate <= 0:
        features = {name: None for name in _SCALAR_NAMES}
        return SignalFingerprint(
            version=FINGERPRINT_VERSION,
            dimensions=EMBEDDING_BINS + len(_SCALAR_NAMES),
            vector=[0.0] * (EMBEDDING_BINS + len(_SCALAR_NAMES)),
            embedding=[0.0] * EMBEDDING_BINS,
            features=features,
            evidence=["Insufficient samples for a fingerprint."],
            warnings=["Fingerprint is empty because the analysed window is too short."],
        )

    embedding, spread = _psd_shape_embedding(work, float(sample_rate))
    if spread <= 1e-9:
        warnings.append("PSD is flat; the shape embedding carries no information.")

    feats = extract_spectral_features(work, float(sample_rate))

    obw = feats.occupied_bandwidth_hz.value
    flatness = feats.spectral_flatness.value
    crest = feats.crest_factor.value
    zcr = feats.zero_crossing_rate.value
    snr = feats.snr_db.value
    drift = feats.frequency_drift_rate.value

    scalar_map: dict[str, float | None] = {
        "occupied_bandwidth_ratio": (
            _clamp01(float(obw) / float(sample_rate)) if obw is not None else None
        ),
        "spectral_flatness": _clamp01(float(flatness)) if flatness is not None else None,
        # Crest factor of a constant-modulus PSK signal sits near 1; noise and
        # sparse bursts push it higher, so 6 is a practical normaliser.
        "crest_factor_norm": _clamp01(float(crest) / 6.0) if crest is not None else None,
        "zero_crossing_rate": _clamp01(float(zcr)) if zcr is not None else None,
        "snr_norm": _clamp01(float(snr) / 50.0) if snr is not None else None,
        # Drift above ~2% of the sample rate per second is already extreme.
        "drift_ratio": (
            _clamp01(abs(float(drift)) / (float(sample_rate) * 0.02))
            if drift is not None
            else None
        ),
    }

    # Unknown scalars are centred at 0 (i.e. "no information") instead of being
    # silently treated as a measurement of zero.
    scalars = np.array(
        [2.0 * value - 1.0 if value is not None else 0.0 for value in scalar_map.values()],
        dtype=float,
    )

    if any(value is None for value in scalar_map.values()):
        warnings.append("One or more scalar features were unavailable; they were centred.")

    vector = np.concatenate(
        [
            EMBEDDING_WEIGHT * _unit_vector(np.asarray(embedding, dtype=float)),
            FEATURE_WEIGHT * _unit_vector(scalars),
        ]
    )
    vector = _unit_vector(vector)

    return SignalFingerprint(
        version=FINGERPRINT_VERSION,
        dimensions=int(vector.size),
        vector=[round(float(v), 6) for v in vector],
        embedding=[round(float(v), 6) for v in embedding],
        features={name: (round(float(value), 6) if value is not None else None)
                  for name, value in scalar_map.items()},
        evidence=[
            "Shape-normalised Welch PSD resampled to 16 normalised-frequency bins",
            "Scalar spectral features (bandwidth ratio, flatness, crest, ZCR, SNR, drift)",
            "Cosine distance over the concatenated unit vector",
        ],
        warnings=warnings,
    )


def fingerprint_distance(a: SignalFingerprint | list[float], b: SignalFingerprint | list[float]) -> float:
    """Cosine distance in [0, 2]; 0 is identical shape, 1 is unrelated."""

    va = np.asarray(a.vector if isinstance(a, SignalFingerprint) else a, dtype=float)
    vb = np.asarray(b.vector if isinstance(b, SignalFingerprint) else b, dtype=float)
    if va.size == 0 or vb.size == 0 or va.size != vb.size:
        raise ValueError("fingerprint vectors are empty or have different dimensions")

    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom <= 1e-12:
        return 1.0
    similarity = float(np.dot(va, vb) / denom)
    return float(np.clip(1.0 - similarity, 0.0, 2.0))
