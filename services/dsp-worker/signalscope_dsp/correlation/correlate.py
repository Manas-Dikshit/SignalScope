from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CorrelationMatch:
    offset: int
    score: float
    hamming_distance: int | None = None


def autocorrelate_bits(bits: np.ndarray, max_lag: int | None = None) -> np.ndarray:
    """Normalized autocorrelation of {0,1} bits (mapped to {-1,+1}) via FFT.

    Identical output to the naive O(N * lag) loop it replaces: linear
    (non-circular) autocorrelation, normalized by max abs value. Lags beyond
    the input length read as 0, matching the old loop's empty-overlap sums.
    """
    x = bits.astype(np.float64) * 2 - 1  # map {0,1} -> {-1,+1}
    n = len(x)
    max_lag = max_lag or n // 2
    if n == 0:
        return np.zeros(max_lag)
    size = 1
    while size < 2 * n - 1:
        size *= 2
    spectrum = np.abs(np.fft.rfft(x, n=size)) ** 2
    corr = np.fft.irfft(spectrum, n=size)[:n]
    if max_lag > n:
        corr = np.concatenate([corr, np.zeros(max_lag - n)])
    else:
        corr = corr[:max_lag]
    return corr / (np.max(np.abs(corr)) + 1e-12)


def cross_correlate_bits(bits_a: np.ndarray, bits_b: np.ndarray) -> np.ndarray:
    a = bits_a.astype(np.float64) * 2 - 1
    b = bits_b.astype(np.float64) * 2 - 1
    corr = np.correlate(a, b, mode="full")
    return corr / (np.max(np.abs(corr)) + 1e-12)


def sliding_pattern_match(bits: np.ndarray, pattern: np.ndarray, tolerance_bits: int = 0,
                           bit_order: str = "msb_first") -> list[CorrelationMatch]:
    """Vectorized sliding-window search: same matches/scores as the naive loop
    (ascending offsets, score = 1 - hamming/len), computed with one strided
    comparison instead of a Python loop per offset."""
    if bit_order == "lsb_first":
        pattern = pattern[::-1]
    p_len = len(pattern)
    n_windows = len(bits) - p_len + 1
    if p_len == 0 or n_windows <= 0:
        return []
    windows = np.lib.stride_tricks.sliding_window_view(bits, p_len)
    hamming = np.sum(windows != pattern, axis=1)
    offsets = np.where(hamming <= tolerance_bits)[0]
    denom = max(p_len, 1)
    return [
        CorrelationMatch(offset=int(o), score=1.0 - int(hamming[o]) / denom,
                         hamming_distance=int(hamming[o]))
        for o in offsets
    ]


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
