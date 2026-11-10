from __future__ import annotations

"""Scientific candidate prioritization for celestial astronomical signals.

Ranks the caller's analysed projects (each project is one candidate signal)
by a transparent, explainable score. Every input comes from data already
stored by the deterministic DSP pipeline:

- ``novelty``       — fingerprint distance to the nearest gallery neighbour
- ``repeatability`` — number of gallery observations that repeat the signal
- ``plausibility``  — narrowband / slow-drift / structured / SNR checklist over
                      stored spectral fingerprint features
- ``feasibility``   — can this candidate realistically be followed up
                      (centre frequency recorded, re-detectable SNR, usable
                      duration, a modulation hypothesis to verify)

Missing inputs score a neutral 0.5 and say so in ``reasons``. Nothing here is
an identification: like the rare-signal gallery, this is a triage heuristic.
"""

from dataclasses import dataclass, field
from typing import Any

# Unknown inputs score neutral so one missing field neither sinks nor
# inflates a candidate; the reason string makes the gap explicit.
UNKNOWN = 0.5

WEIGHTS = {
    "novelty": 0.30,
    "plausibility": 0.25,
    "repeatability": 0.25,
    "feasibility": 0.20,
}

# Fingerprint features below this SNR norm (~10 dB) are treated as too weak to
# re-detect or to trust for structure checks.
_SNR_NORM_FLOOR = 0.2

# A fingerprint at or below this distance counts as a repeat observation
# (defaults to the rare-signal threshold; overridden per call).
_REPEAT_DISTANCE = 0.35


@dataclass
class CandidateFacts:
    """One candidate's stored evidence, pre-digested by the caller."""

    project_id: str
    project_name: str
    created_at: str | None = None
    features: dict[str, float | None] = field(default_factory=dict)
    estimates: dict[str, dict[str, Any]] = field(default_factory=dict)
    gallery_size: int = 0
    nearest_distance: float | None = None
    repeat_count: int = 0
    duration_seconds: float | None = None
    center_frequency_hz: float | None = None


def _feature(features: dict[str, float | None], name: str) -> float | None:
    value = features.get(name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _snr_norm(features: dict[str, float | None]) -> float | None:
    return _feature(features, "snr_norm")


def score_novelty(facts: CandidateFacts, threshold: float) -> tuple[float, list[str]]:
    if facts.gallery_size == 0 or facts.nearest_distance is None:
        return UNKNOWN, [
            "Novelty unknown: no comparable fingerprinted observation exists yet."
        ]
    nearest = facts.nearest_distance
    if nearest > threshold:
        return 1.0, [
            f"No similar observation in the gallery (nearest distance "
            f"{nearest:.2f} > threshold {threshold:.2f}); rare-signal candidate."
        ]
    score = min(1.0, nearest / threshold) if threshold > 0 else 0.0
    return score, [
        f"Nearest gallery neighbour at distance {nearest:.2f} "
        f"(threshold {threshold:.2f}); closer to known evidence means less novel."
    ]


def score_repeatability(facts: CandidateFacts, threshold: float) -> tuple[float, list[str]]:
    if facts.gallery_size == 0 or facts.nearest_distance is None:
        return UNKNOWN, [
            "Repeatability unknown: no comparable fingerprinted observation exists yet."
        ]
    if facts.repeat_count <= 0:
        return 0.0, ["Signal has not re-appeared in any gallery observation yet."]
    score = min(1.0, facts.repeat_count / 2.0)
    return score, [
        f"Re-detected in {facts.repeat_count} other observation(s) within the "
        f"repeat threshold ({threshold:.2f})."
    ]


def score_plausibility(facts: CandidateFacts) -> tuple[float, list[str]]:
    """Checklist over stored fingerprint features; celestial-source proxies."""
    checks: list[tuple[float, str]] = []

    obw = _feature(facts.features, "occupied_bandwidth_ratio")
    if obw is None:
        checks.append((UNKNOWN, "Occupied bandwidth unknown."))
    elif obw <= 0.1:
        checks.append((1.0, f"Narrowband: occupies {obw * 100:.0f}% of the captured band."))
    elif obw <= 0.3:
        checks.append((UNKNOWN, f"Moderately wideband ({obw * 100:.0f}% of the band)."))
    else:
        checks.append((0.0, f"Wideband ({obw * 100:.0f}% of the band): more like broadband interference."))

    drift = _feature(facts.features, "drift_ratio")
    if drift is None:
        checks.append((UNKNOWN, "Frequency drift unknown."))
    elif drift <= 0.25:
        checks.append((1.0, "Drift is slow relative to the band, consistent with sky-motion Doppler."))
    else:
        checks.append((0.0, "Drift is fast relative to the band, more like an unstable local oscillator."))

    flatness = _feature(facts.features, "spectral_flatness")
    if flatness is None:
        checks.append((UNKNOWN, "Spectral flatness unknown."))
    elif flatness <= 0.5:
        checks.append((1.0, "Structured (tonal) spectrum rather than noise-like."))
    else:
        checks.append((0.0, "Noise-like flat spectrum."))

    snr = _snr_norm(facts.features)
    if snr is None:
        checks.append((UNKNOWN, "SNR unknown."))
    elif snr >= _SNR_NORM_FLOOR:
        checks.append((1.0, "SNR is strong enough for a coherent emitter."))
    else:
        checks.append((0.0, "SNR is very weak; structure is not trustworthy."))

    score = sum(value for value, _ in checks) / len(checks)
    return score, [reason for _, reason in checks]


def score_feasibility(facts: CandidateFacts) -> tuple[float, list[str]]:
    checks: list[tuple[float, str]] = []

    if facts.center_frequency_hz:
        checks.append((1.0, f"Centre frequency recorded ({facts.center_frequency_hz:,.0f} Hz); re-pointing possible."))
    else:
        checks.append((0.0, "No centre frequency metadata; the band cannot be re-pointed."))

    snr = _snr_norm(facts.features)
    if snr is None:
        checks.append((UNKNOWN, "Re-detectability unknown (no SNR estimate)."))
    elif snr >= _SNR_NORM_FLOOR:
        checks.append((1.0, "Strong enough to re-detect on a follow-up observation."))
    else:
        checks.append((0.0, "Too weak for a confident re-detection."))

    duration = facts.duration_seconds
    if duration is None:
        checks.append((UNKNOWN, "Duration unknown."))
    elif 1.0 <= duration <= 7200.0:
        checks.append((1.0, f"Duration ({duration:,.0f} s) fits a practical re-observation window."))
    else:
        checks.append((0.0, f"Duration ({duration:,.0f} s) is impractical for re-observation."))

    if "modulation" in facts.estimates:
        checks.append((1.0, "A modulation hypothesis exists to verify on follow-up."))
    else:
        checks.append((0.0, "No modulation hypothesis yet; nothing specific to verify."))

    score = sum(value for value, _ in checks) / len(checks)
    return score, [reason for _, reason in checks]


def score_candidate(facts: CandidateFacts, threshold: float = _REPEAT_DISTANCE) -> dict[str, Any]:
    novelty, novelty_reasons = score_novelty(facts, threshold)
    repeatability, repeat_reasons = score_repeatability(facts, threshold)
    plausibility, plausibility_reasons = score_plausibility(facts)
    feasibility, feasibility_reasons = score_feasibility(facts)

    composite = 100.0 * (
        WEIGHTS["novelty"] * novelty
        + WEIGHTS["plausibility"] * plausibility
        + WEIGHTS["repeatability"] * repeatability
        + WEIGHTS["feasibility"] * feasibility
    )

    rare_signal: bool | None = None
    if facts.nearest_distance is not None:
        rare_signal = facts.nearest_distance > threshold

    return {
        "project_id": facts.project_id,
        "project_name": facts.project_name,
        "created_at": facts.created_at,
        "composite": round(composite, 1),
        "novelty": round(novelty, 3),
        "repeatability": round(repeatability, 3),
        "plausibility": round(plausibility, 3),
        "feasibility": round(feasibility, 3),
        "repeats": facts.repeat_count,
        "nearest_distance": facts.nearest_distance,
        "rare_signal": rare_signal,
        "reasons": novelty_reasons + repeat_reasons + plausibility_reasons + feasibility_reasons,
    }


def prioritize(
    facts_list: list[CandidateFacts], threshold: float = _REPEAT_DISTANCE
) -> list[dict[str, Any]]:
    ranked = [score_candidate(facts, threshold) for facts in facts_list]
    ranked.sort(key=lambda item: (-item["composite"], item["project_name"]))
    return ranked


METHOD = (
    "Transparent weighted checklist over stored DSP evidence: novelty and "
    "repeatability from fingerprint gallery distances, astrophysical "
    "plausibility from spectral features (bandwidth, drift, flatness, SNR), "
    "and follow-up feasibility from metadata. A triage heuristic, not an "
    "identification."
)

EVIDENCE = [
    "Novelty: cosine distance to the nearest fingerprint in the caller's own gallery",
    "Repeatability: count of gallery observations within the repeat distance threshold",
    "Plausibility: occupied bandwidth, drift rate, spectral flatness, and SNR checks",
    "Feasibility: centre frequency recorded, re-detectable SNR, usable duration, modulation hypothesis",
    "Missing inputs score a neutral 0.5 and are listed in the reasons",
]
