from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..common import Estimate, Source

SUPPORTED_LABELS = ["OOK/ASK", "2-FSK", "4-FSK", "BPSK", "QPSK", "8-PSK", "16-QAM", "64-QAM", "unknown"]


@dataclass
class ModulationHypothesis:
    label: str
    confidence: float
    evidence: list[str] = field(default_factory=list)


def _envelope_variance(samples: np.ndarray) -> float:
    mag = np.abs(samples)
    m = np.mean(mag)
    return float(np.var(mag) / (m ** 2 + 1e-12))


def _freq_cluster_count(inst_freq: np.ndarray, sample_rate: float, max_clusters: int = 4) -> tuple[int, list[float]]:
    """Very lightweight 1D clustering of instantaneous frequency via histogram peak-finding.
    Used to distinguish M-FSK's discrete tones from PSK's continuous phase ramps."""
    hist, edges = np.histogram(inst_freq, bins=64)
    hist = hist / max(hist.sum(), 1)
    peaks = []
    for i in range(1, len(hist) - 1):
        if hist[i] > hist[i - 1] and hist[i] >= hist[i + 1] and hist[i] > 0.03:
            peaks.append((edges[i] + edges[i + 1]) / 2)
    peaks = sorted(peaks)
    # merge peaks that are very close together
    merged: list[float] = []
    for p in peaks:
        if merged and abs(p - merged[-1]) < sample_rate * 0.01:
            continue
        merged.append(p)
    return len(merged), merged


def _mth_power_peakiness(samples: np.ndarray, m: int) -> float:
    """Classic M-th power method: raising a PSK signal with order M to the M-th power
    collapses the M phase states onto a single tone, producing a sharp spectral peak.
    Returns a 0..1 'peakiness' score (peak power / mean power of the spectrum),
    calibrated so a pure Hann-windowed tone scores ~0.9 and white noise ~0.0:
    a pure tone gives peak/mean ≈ 0.665 * N (length-invariant, measured), so the
    constant 3.5 maps it to 1 - exp(-3.5 * 0.665) ≈ 0.90."""
    raised = samples ** m
    spectrum = np.abs(np.fft.fft(raised * np.hanning(len(raised))))
    power = spectrum ** 2
    peak = np.max(power)
    mean = np.mean(power)
    if mean <= 0:
        return 0.0
    ratio = peak / mean
    # squash into 0..1 with a calibrated ceiling (see docstring)
    return float(1 - np.exp(-3.5 * ratio / len(samples)))


def _ring_count(samples: np.ndarray, n_bins: int = 32) -> int:
    """Count amplitude 'rings' present in the signal, distinguishing constant-envelope
    modulations (1 ring) from multi-amplitude schemes like QAM/ASK."""
    mag = np.abs(samples)
    mag = mag[mag > 1e-6]
    if len(mag) == 0:
        return 0
    hist, _ = np.histogram(mag, bins=n_bins)
    hist = hist / max(hist.sum(), 1)
    peaks = 0
    for i in range(1, len(hist) - 1):
        if hist[i] > hist[i - 1] and hist[i] >= hist[i + 1] and hist[i] > 0.05:
            peaks += 1
    return max(peaks, 1)


def classify_modulation(samples: np.ndarray, sample_rate: float) -> list[ModulationHypothesis]:
    """Hybrid rule-based classifier producing top-k ranked hypotheses with evidence.

    This MVP intentionally uses transparent, explainable handcrafted features rather
    than an opaque neural classifier, per the project's explainability requirement.
    A learned classifier can be layered on top later without changing this interface.
    """
    if len(samples) < 64:
        return [ModulationHypothesis("unknown", 0.4, ["Recording/segment too short to classify reliably."])]

    env_var = _envelope_variance(samples)
    inst_phase = np.unwrap(np.angle(samples))
    inst_freq = np.diff(inst_phase) * sample_rate / (2 * np.pi)
    n_tones, tone_freqs = _freq_cluster_count(inst_freq, sample_rate)
    rings = _ring_count(samples)

    scores: dict[str, ModulationHypothesis] = {}

    def add(label, confidence, evidence):
        confidence = float(np.clip(confidence, 0.0, 0.98))
        if label not in scores or confidence > scores[label].confidence:
            scores[label] = ModulationHypothesis(label, confidence, evidence)

    constant_envelope = env_var < 0.05

    if constant_envelope:
        if n_tones == 2:
            add("2-FSK", 0.55 + 0.3 * min(n_tones / 2, 1),
                [f"Constant envelope (var={env_var:.3f}); {n_tones} discrete instantaneous-frequency clusters at {['%.0f'%f for f in tone_freqs]} Hz"])
        elif n_tones in (3, 4):
            add("4-FSK", 0.5 + 0.1 * n_tones,
                [f"Constant envelope; {n_tones} instantaneous-frequency clusters detected"])

        p2 = _mth_power_peakiness(samples, 2)
        p4 = _mth_power_peakiness(samples, 4)
        p8 = _mth_power_peakiness(samples, 8)
        # Differential scoring: a lower-order peak already explains any higher-order
        # peak (e.g. BPSK squared is a pure tone, whose 4th/8th powers are tones too),
        # so higher-order hypotheses only earn confidence from *unexplained* peakiness.
        # Without this, BPSK and QPSK tie on BPSK input.
        add("BPSK", 0.3 + 0.6 * p2, [f"2nd-power spectral peakiness={p2:.2f} (BPSK collapses to a single tone under squaring)"])
        add("QPSK", 0.3 + 0.6 * p4 * (1 - p2), [f"4th-power spectral peakiness={p4:.2f} beyond 2nd-power (QPSK collapses to a single tone under 4th power)"])
        add("8-PSK", 0.25 + 0.55 * p8 * (1 - max(p2, p4)), [f"8th-power spectral peakiness={p8:.2f} beyond 2nd/4th-power"])
    else:
        if rings <= 2:
            add("OOK/ASK", 0.5 + 0.1 * rings, [f"Non-constant envelope (var={env_var:.3f}); {rings} amplitude level(s) detected"])
        elif rings <= 4:
            add("16-QAM", 0.45 + 0.05 * rings, [f"Non-constant envelope; {rings} amplitude rings detected (consistent with 16-QAM)"])
        else:
            add("64-QAM", 0.4, [f"Non-constant envelope; {rings} amplitude rings detected (consistent with a higher-order QAM)"])
        # QAM constellations still show weak 4th-power peakiness from the QPSK-like quadrant structure.
        # Only relevant when multiple amplitude rings are present (pure OOK/ASK also
        # shows strong M-th-power peakiness from its on/off carrier, which must NOT
        # be misread as PSK evidence). Threshold 0.5 on the calibrated 0..1 scale:
        # clean 16/64-QAM score ~0.2-0.3, clean QPSK ~0.9.
        p4 = _mth_power_peakiness(samples, 4)
        if rings > 2 and p4 > 0.5:
            add("QPSK", 0.2 + 0.3 * p4, [f"Some 4th-power peakiness ({p4:.2f}) despite amplitude variation; check for QAM vs QPSK+noise"])

    if not scores:
        scores["unknown"] = ModulationHypothesis("unknown", 0.4, ["No feature crossed classification thresholds."])

    ranked = sorted(scores.values(), key=lambda h: h.confidence, reverse=True)
    # normalize so top-3 confidences are legible relative probabilities, but never claim exactness
    return ranked[:3]


def classify_modulation_estimate(samples: np.ndarray, sample_rate: float) -> Estimate:
    hyps = classify_modulation(samples, sample_rate)
    top = hyps[0]
    alternatives = [
        Estimate(name="modulation", value=h.label, source=Source.HYPOTHESIS, confidence=h.confidence, evidence=h.evidence)
        for h in hyps[1:]
    ]
    return Estimate(
        name="modulation", value=top.label, source=Source.HYPOTHESIS, confidence=top.confidence,
        evidence=top.evidence, alternatives=alternatives,
        warnings=["Modulation classification is a hypothesis based on handcrafted features, not a certainty."],
    )
