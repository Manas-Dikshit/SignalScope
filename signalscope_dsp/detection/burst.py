from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as sp_signal

from ..common import Estimate, Source


@dataclass
class Burst:
    start_sample: int
    end_sample: int
    start_time_s: float
    end_time_s: float
    peak_power_db: float
    mean_power_db: float
    confidence: float


def detect_bursts(samples: np.ndarray, sample_rate: float, smoothing_ms: float = 1.0,
                   threshold_db_above_floor: float = 6.0, min_burst_ms: float = 0.5,
                   min_gap_ms: float = 0.2) -> list[Burst]:
    """Energy-based adaptive-threshold burst detector.

    Envelope power is smoothed, a noise floor is estimated from the lower
    percentile of the envelope, and contiguous regions exceeding
    (floor + threshold_db_above_floor) are reported as bursts. Short bursts and
    small gaps are merged/dropped per the min_* parameters.
    """
    power = np.abs(samples) ** 2
    win_samples = max(1, int(sample_rate * smoothing_ms / 1000.0))
    kernel = np.ones(win_samples) / win_samples
    smoothed = np.convolve(power, kernel, mode="same")
    smoothed_db = 10 * np.log10(smoothed + 1e-20)

    noise_floor_db = float(np.percentile(smoothed_db, 20))
    threshold = noise_floor_db + threshold_db_above_floor
    active = smoothed_db > threshold

    # find contiguous regions
    edges = np.diff(active.astype(np.int8))
    starts = list(np.where(edges == 1)[0] + 1)
    ends = list(np.where(edges == -1)[0] + 1)
    if active[0]:
        starts = [0] + starts
    if active[-1]:
        ends = ends + [len(active)]

    min_burst_samples = int(sample_rate * min_burst_ms / 1000.0)
    min_gap_samples = int(sample_rate * min_gap_ms / 1000.0)

    regions = [(s, e) for s, e in zip(starts, ends) if e - s >= min_burst_samples]

    # merge regions separated by small gaps
    merged: list[list[int]] = []
    for s, e in regions:
        if merged and s - merged[-1][1] <= min_gap_samples:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    bursts = []
    for s, e in merged:
        seg_db = smoothed_db[s:e]
        peak = float(np.max(seg_db))
        mean = float(np.mean(seg_db))
        margin = peak - threshold
        confidence = float(np.clip(margin / 20.0, 0.3, 0.99))
        bursts.append(Burst(
            start_sample=int(s), end_sample=int(e),
            start_time_s=s / sample_rate, end_time_s=e / sample_rate,
            peak_power_db=peak, mean_power_db=mean, confidence=confidence,
        ))
    return bursts


def burst_stats(bursts: list[Burst]) -> dict:
    if not bursts:
        return {
            "burst_duration_s": Estimate("burst_duration", None, "s", Source.UNKNOWN,
                                          warnings=["No bursts detected above threshold."]),
            "repetition_interval_s": Estimate("repetition_interval", None, "s", Source.UNKNOWN),
            "duty_cycle": Estimate("duty_cycle", None, None, Source.UNKNOWN),
        }
    durations = [b.end_time_s - b.start_time_s for b in bursts]
    mean_duration = float(np.mean(durations))
    result = {
        "burst_duration_s": Estimate("burst_duration", mean_duration, "s", Source.MEASURED,
                                      evidence=[f"mean of {len(bursts)} detected burst(s)"]),
    }
    if len(bursts) > 1:
        gaps = [bursts[i + 1].start_time_s - bursts[i].start_time_s for i in range(len(bursts) - 1)]
        rep = float(np.mean(gaps))
        result["repetition_interval_s"] = Estimate("repetition_interval", rep, "s", Source.ESTIMATED,
                                                     confidence=0.6,
                                                     evidence=["mean spacing between burst onsets"])
        total_span = bursts[-1].end_time_s - bursts[0].start_time_s
        duty = float(np.sum(durations) / total_span) if total_span > 0 else None
        result["duty_cycle"] = Estimate("duty_cycle", duty, None, Source.ESTIMATED, confidence=0.6)
    else:
        result["repetition_interval_s"] = Estimate("repetition_interval", None, "s", Source.UNKNOWN,
                                                     warnings=["Only one burst detected; no repetition interval."])
        result["duty_cycle"] = Estimate("duty_cycle", None, None, Source.UNKNOWN)
    return result
