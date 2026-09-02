from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CorrelationMatch:
    offset: int
    score: float
    hamming_distance: int | None = None


def autocorrelate_bits(bits: np.ndarray, max_lag: int | None = None) -> np.ndarray:
    x = bits.astype(np.float64) * 2 - 1  # map {0,1} -> {-1,+1}
    n = len(x)
    max_lag = max_lag or n // 2
    result = np.zeros(max_lag)
    for lag in range(max_lag):
        if lag == 0:
            result[lag] = np.sum(x * x)
        else:
            result[lag] = np.sum(x[:-lag] * x[lag:])
    return result / (np.max(np.abs(result)) + 1e-12)


def cross_correlate_bits(bits_a: np.ndarray, bits_b: np.ndarray) -> np.ndarray:
    a = bits_a.astype(np.float64) * 2 - 1
    b = bits_b.astype(np.float64) * 2 - 1
    corr = np.correlate(a, b, mode="full")
    return corr / (np.max(np.abs(corr)) + 1e-12)


def sliding_pattern_match(bits: np.ndarray, pattern: np.ndarray, tolerance_bits: int = 0,
                           bit_order: str = "msb_first") -> list[CorrelationMatch]:
    if bit_order == "lsb_first":
        pattern = pattern[::-1]
    matches = []
    p_len = len(pattern)
    for offset in range(len(bits) - p_len + 1):
        window = bits[offset: offset + p_len]
        hd = int(np.sum(window != pattern))
        if hd <= tolerance_bits:
            score = 1.0 - hd / max(p_len, 1)
            matches.append(CorrelationMatch(offset=offset, score=score, hamming_distance=hd))
    return matches


def find_repeated_sequences(bits: np.ndarray, seq_length: int, min_repeats: int = 2) -> list[dict]:
    """Detect header/preamble repetition by hashing fixed-length windows and reporting
    any pattern that recurs at least min_repeats times."""
    if len(bits) < seq_length:
        return []
    seen: dict[bytes, list[int]] = {}
    for offset in range(len(bits) - seq_length + 1):
        key = np.packbits(bits[offset: offset + seq_length]).tobytes()
        seen.setdefault(key, []).append(offset)
    results = []
    for key, offsets in seen.items():
        if len(offsets) >= min_repeats:
            results.append({
                "pattern_hex": key.hex(),
                "offsets": offsets,
                "repeat_count": len(offsets),
            })
    results.sort(key=lambda r: r["repeat_count"], reverse=True)
    return results
