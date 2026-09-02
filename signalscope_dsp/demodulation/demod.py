from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# --- Gray-coded reference constellations -----------------------------------

def _psk_constellation(order: int) -> np.ndarray:
    k = int(np.log2(order))
    angles = 2 * np.pi * np.arange(order) / order
    return np.exp(1j * angles)


def _gray_code(n_bits: int) -> list[int]:
    return [(i ^ (i >> 1)) for i in range(2 ** n_bits)]


def _qam_constellation(order: int) -> np.ndarray:
    """Ordered so that symbol index k = i_idx*side + q_idx, matching the synthetic
    generator's direct (non-Gray) bit-to-symbol mapping."""
    side = int(np.sqrt(order))
    levels = np.arange(-(side - 1), side, 2)
    points = np.array([complex(levels[i], levels[q]) for i in range(side) for q in range(side)])
    points = points / np.max(np.abs(points))
    return points


@dataclass
class DemodResult:
    hard_bits: np.ndarray            # 0/1 array
    soft_bits: np.ndarray | None     # LLR-like soft values, same length*bits_per_symbol
    symbols: np.ndarray              # complex decided symbol values
    symbol_indices: np.ndarray       # index into constellation
    samples_per_symbol: int
    bits_per_symbol: int
    warnings: list[str] = field(default_factory=list)


def _slice_to_symbols(samples: np.ndarray, samples_per_symbol: int, symbol_offset: int = 0) -> np.ndarray:
    """Decimate to one representative sample per symbol period (naive center-sample
    timing — this MVP does not yet implement a full Gardner/Mueller-and-Muller timing
    recovery loop; for real captures with timing drift, results will degrade)."""
    if samples_per_symbol < 1:
        raise ValueError("samples_per_symbol must be >= 1")
    center = samples_per_symbol // 2 + symbol_offset
    n_symbols = (len(samples) - center) // samples_per_symbol
    idx = center + np.arange(n_symbols) * samples_per_symbol
    idx = idx[idx < len(samples)]
    return samples[idx]


def demod_psk(samples: np.ndarray, order: int, samples_per_symbol: int) -> DemodResult:
    assert order in (2, 4, 8), "PSK order must be 2 (BPSK), 4 (QPSK), or 8 (8-PSK)"
    bits_per_symbol = int(np.log2(order))
    warnings = []
    if len(samples) < samples_per_symbol * 4:
        warnings.append("Very short segment; symbol decisions may be unreliable.")

    sym_samples = _slice_to_symbols(samples, samples_per_symbol)
    ref = _psk_constellation(order)

    # nearest-constellation-point hard decision. Direct (non-Gray) binary mapping:
    # symbol index k directly encodes the k transmitted bits, matching the
    # synthetic generator's convention. (Gray mapping can be added as an option
    # later; it only changes the bit<->symbol lookup table, not the sync/decision
    # machinery.)
    dists = np.abs(sym_samples[:, None] - ref[None, :])
    decisions = np.argmin(dists, axis=1)

    bits = np.zeros((len(decisions), bits_per_symbol), dtype=np.uint8)
    for b in range(bits_per_symbol):
        bits[:, b] = (decisions >> (bits_per_symbol - 1 - b)) & 1
    hard_bits = bits.flatten()

    min_dist = np.min(dists, axis=1)
    second_min = np.partition(dists, 1, axis=1)[:, 1]
    margin = second_min - min_dist
    soft = np.repeat(margin, bits_per_symbol)  # crude LLR-magnitude proxy

    warnings.append(
        "Carrier phase is assumed already recovered / near baseband; no closed-loop "
        "Costas/PLL carrier tracking is applied in this MVP, so residual phase "
        "rotation will show up as elevated error rate."
    )

    return DemodResult(
        hard_bits=hard_bits, soft_bits=soft, symbols=ref[decisions], symbol_indices=decisions,
        samples_per_symbol=samples_per_symbol, bits_per_symbol=bits_per_symbol, warnings=warnings,
    )


def demod_qam(samples: np.ndarray, order: int, samples_per_symbol: int) -> DemodResult:
    assert order in (16, 64)
    bits_per_symbol = int(np.log2(order))
    sym_samples = _slice_to_symbols(samples, samples_per_symbol)

    peak = np.percentile(np.abs(sym_samples), 95)
    if peak > 0:
        sym_samples = sym_samples / peak

    ref = _qam_constellation(order)
    dists = np.abs(sym_samples[:, None] - ref[None, :])
    decisions = np.argmin(dists, axis=1)

    bits = np.zeros((len(decisions), bits_per_symbol), dtype=np.uint8)
    for i, d in enumerate(decisions):
        for b in range(bits_per_symbol):
            bits[i, b] = (d >> (bits_per_symbol - 1 - b)) & 1
    hard_bits = bits.flatten()

    min_dist = np.min(dists, axis=1)
    second_min = np.partition(dists, 1, axis=1)[:, 1]
    soft = np.repeat(second_min - min_dist, bits_per_symbol)

    return DemodResult(
        hard_bits=hard_bits, soft_bits=soft, symbols=ref[decisions], symbol_indices=decisions,
        samples_per_symbol=samples_per_symbol, bits_per_symbol=bits_per_symbol,
        warnings=["AGC applied via 95th-percentile amplitude normalization; no closed-loop carrier/timing recovery yet."],
    )


def demod_fsk(samples: np.ndarray, sample_rate: float, order: int, samples_per_symbol: int,
              deviation_hz: float | None = None) -> DemodResult:
    """Quadrature (frequency-discriminator) FSK demod. For 2-FSK, decides based on the
    sign of instantaneous frequency relative to its mean; for M-FSK, clusters the
    per-symbol mean instantaneous frequency against evenly spaced tone hypotheses."""
    bits_per_symbol = int(np.log2(order))
    phase = np.unwrap(np.angle(samples))
    inst_freq = np.diff(phase) * sample_rate / (2 * np.pi)
    inst_freq = np.concatenate([inst_freq[:1], inst_freq])  # keep same length, preserve sample alignment

    # Average over each symbol's own sample span (not a window centered between
    # symbols, which would straddle a tone transition and wash out the average
    # whenever adjacent symbols differ). A small guard trims the first/last few
    # samples of each span to reduce sensitivity to any residual edge transient.
    n_symbols = len(inst_freq) // samples_per_symbol
    guard = max(1, samples_per_symbol // 5)
    sym_freqs = np.array([
        np.mean(inst_freq[i * samples_per_symbol + guard: (i + 1) * samples_per_symbol - guard])
        for i in range(n_symbols)
    ])

    mean_f = np.mean(sym_freqs)
    if order == 2:
        decisions = (sym_freqs > mean_f).astype(int)
        tones = np.array([mean_f - abs(deviation_hz or np.std(sym_freqs)), mean_f + abs(deviation_hz or np.std(sym_freqs))])
    else:
        span = np.max(sym_freqs) - np.min(sym_freqs)
        tones = np.linspace(np.min(sym_freqs), np.max(sym_freqs), order) if span > 0 else np.zeros(order)
        decisions = np.argmin(np.abs(sym_freqs[:, None] - tones[None, :]), axis=1)

    bits = np.zeros((len(decisions), bits_per_symbol), dtype=np.uint8)
    for b in range(bits_per_symbol):
        bits[:, b] = (decisions >> (bits_per_symbol - 1 - b)) & 1

    return DemodResult(
        hard_bits=bits.flatten(), soft_bits=None, symbols=tones[decisions].astype(complex),
        symbol_indices=decisions, samples_per_symbol=samples_per_symbol, bits_per_symbol=bits_per_symbol,
        warnings=["Tone frequencies estimated from the data itself (min/max of per-symbol instantaneous "
                  "frequency) unless a deviation was supplied; treat as a hypothesis for M>2."],
    )
