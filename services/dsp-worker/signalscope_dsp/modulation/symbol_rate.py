from __future__ import annotations

import numpy as np

from ..common import Estimate, Source


def estimate_symbol_rate_candidates(samples: np.ndarray, sample_rate: float, min_rate_hz: float = 50.0,
                                     max_candidates: int = 3) -> list[Estimate]:
    """Cyclostationary-style symbol-rate estimate: the spectrum of |signal|^2 (or the
    signal's squared magnitude) typically shows a peak near the symbol rate for many
    digital modulations, since amplitude/phase transitions repeat at the symbol clock.

    Returns multiple candidates when evidence is ambiguous, per the spec's requirement
    to return candidates rather than asserting a single value from noisy/short data.
    """
    if len(samples) < 32 or not sample_rate:
        return [Estimate("symbol_rate", None, "Hz", Source.UNKNOWN,
                          warnings=["Recording too short or sample rate unknown."])]

    # |diff(samples)|^2 rather than |samples|^2: constant-envelope modulations
    # (PSK, FSK) have no amplitude-domain symbol-rate line, but every symbol
    # transition still produces a sample-to-sample jump, so the *difference*
    # signal carries a spectral line at the symbol rate for both constant- and
    # non-constant-envelope signals alike.
    nonlinear = np.abs(np.diff(samples)) ** 2
    nonlinear = nonlinear - np.mean(nonlinear)
    spectrum = np.abs(np.fft.rfft(nonlinear * np.hanning(len(nonlinear))))
    freqs = np.fft.rfftfreq(len(nonlinear), d=1.0 / sample_rate)

    min_idx = np.searchsorted(freqs, min_rate_hz)
    max_idx = np.searchsorted(freqs, sample_rate / 2.2)  # stay well under Nyquist/2 as a sane symbol-rate ceiling
    if max_idx <= min_idx:
        return [Estimate("symbol_rate", None, "Hz", Source.UNKNOWN, warnings=["Search band collapsed; recording likely too short."])]

    search_band = spectrum[min_idx:max_idx]
    search_freqs = freqs[min_idx:max_idx]
    if len(search_band) == 0 or np.max(search_band) == 0:
        return [Estimate("symbol_rate", None, "Hz", Source.UNKNOWN)]

    order = np.argsort(search_band)[::-1]
    candidates = []
    seen_freqs: list[float] = []
    total_power = np.sum(search_band) + 1e-12
    for idx in order:
        f = float(search_freqs[idx])
        if any(abs(f - sf) < min_rate_hz for sf in seen_freqs):
            continue
        seen_freqs.append(f)
        conf = float(np.clip(search_band[idx] / total_power * 10, 0.1, 0.9))
        candidates.append(Estimate(
            name="symbol_rate", value=round(f, 1), unit="Hz", source=Source.ESTIMATED, confidence=conf,
            evidence=["Spectral peak of |signal|^2 (cyclostationary symbol-clock feature)"],
        ))
        if len(candidates) >= max_candidates:
            break

    if not candidates:
        return [Estimate("symbol_rate", None, "Hz", Source.UNKNOWN)]
    return candidates
