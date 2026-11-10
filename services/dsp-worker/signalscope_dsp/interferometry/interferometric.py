"""Multi-antenna (interferometric) origin discrimination — one output.

Correlating the signal received simultaneously on two (or more) antennas lets
the system answer a single question with a single Estimate: does the dominant
signal follow a single, propagation-consistent path from the sky ("sky"), or
does it look local to the observatory ("near_field_observatory" — reflections,
excess delay, incoherent phase)?

Method (all measured from the data, always an Estimate, never a certainty):
- Cross-spectral coherence between antennas tells whether they share the
  signal at all (no shared component -> "inconclusive", not a verdict).
- For a far-field (sky) source the cross-spectrum phase is linear in
  frequency, with slope 2*pi*tau for a single geometric delay; fitting that
  line measures the interferometric delay tau.
- Non-linear phase (multipath-style delay spread) or a delay beyond the
  baseline/c propagation bound is not reachable by any sky source -> local.

shortcut: the phase-slope delay is only resolvable within half the analyzed
band (|tau| > 0.5/band aliases to a smaller value and can mimic sky).
Upgrade: multi-baseline closure phases or a 3+ antenna rank-1 direction fit.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
from scipy import signal as sp_signal

from ..common import Estimate, Source

C_LIGHT = 299_792_458.0

SKY = "sky"
NEAR_FIELD = "near_field_observatory"
INCONCLUSIVE = "inconclusive"

_MIN_COHERENCE = 0.25   # below this the antennas share no usable signal
_LINEAR_R2 = 0.9        # phase-vs-frequency fits a single geometric delay
_NONLINEAR_R2 = 0.5     # below this the phase looks delay-spread / multipath


def _cross_spectrum(x: np.ndarray, y: np.ndarray, sample_rate: float):
    """(freqs, Pxy, Pxx, Pyy) with fftshift-order (monotonic) frequencies."""
    nperseg = min(1024, len(x))
    noverlap = nperseg // 2
    f, pxy = sp_signal.csd(x, y, fs=sample_rate, nperseg=nperseg, noverlap=noverlap,
                           return_onesided=False)
    _, pxx = sp_signal.welch(x, fs=sample_rate, nperseg=nperseg, noverlap=noverlap,
                             return_onesided=False)
    _, pyy = sp_signal.welch(y, fs=sample_rate, nperseg=nperseg, noverlap=noverlap,
                             return_onesided=False)
    return np.fft.fftshift(f), np.fft.fftshift(pxy), np.fft.fftshift(pxx), np.fft.fftshift(pyy)


def interferometric_origin(
    channels: Sequence[np.ndarray],
    sample_rate: float,
    baseline_m: Optional[float] = None,
) -> Estimate:
    """Interferometric origin verdict: SKY vs NEAR_FIELD vs INCONCLUSIVE.

    `channels` are the simultaneous per-antenna recordings (complex64, equal
    time base). `baseline_m` is the user-supplied antenna separation; when
    given, the measured delay is checked against the baseline/c far-field
    propagation bound and a sky bearing (angle off the baseline axis) is
    reported in the evidence.
    """
    name = "interferometric_origin"
    if channels is None or len(channels) < 2:
        return Estimate(
            name, None, None, Source.UNKNOWN,
            warnings=["Interferometric origin requires >=2 simultaneous antenna "
                      "channels; not available for this recording."])

    x = np.asarray(channels[0]).ravel()
    y = np.asarray(channels[1]).ravel()
    n = min(len(x), len(y))
    if n < 256 or sample_rate <= 0:
        return Estimate(name, None, None, Source.UNKNOWN,
                        warnings=["Recording too short (<256 samples) or sample rate "
                                  "unknown; interferometric analysis not possible."])
    x, y = x[:n], y[:n]

    f, pxy, pxx, pyy = _cross_spectrum(x, y, sample_rate)
    rho = np.abs(pxy) / np.sqrt(np.maximum(pxx * pyy, 1e-30))
    # judge only the signal band: strongest 20% of bins by cross power
    k = max(4, rho.size // 5)
    band = np.sort(np.argsort(rho)[-k:])
    coherence = float(np.mean(rho[band]))

    warnings: list[str] = []
    evidence = [f"Cross-spectral coherence in the signal band: {coherence:.2f} "
                f"(strongest {band.size} of {rho.size} bins)"]

    if coherence < _MIN_COHERENCE:
        warnings.append("No coherent component is shared between the antennas; "
                        "an interferometric verdict is not possible (frequencies "
                        "and gains are uncorrelated).")
        return Estimate(name, INCONCLUSIVE, None, Source.ESTIMATED, confidence=0.2,
                        evidence=evidence, warnings=warnings)
    evidence.append(f"Coherence above the {_MIN_COHERENCE} threshold: a common signal exists.")

    tau = None
    if float(np.var(f[band])) <= 0:
        r2 = 0.0
        warnings.append("Signal band narrower than one resolution cell; "
                        "phase-slope model untestable.")
    else:
        fm = f[band]
        phase = np.unwrap(np.angle(pxy[band]))
        fm_c = fm - fm.mean()
        phase_c = phase - phase.mean()
        delay_slope = float(np.dot(fm_c, phase_c) / np.dot(fm_c, fm_c))  # rad per Hz
        tau = delay_slope / (2 * np.pi)
        pred = delay_slope * fm_c
        total = float(np.sum(phase_c ** 2))
        r2 = 1.0 - float(np.sum((phase_c - pred) ** 2)) / total if total > 0 else 1.0
        evidence.append(
            f"Cross-spectrum phase vs frequency linearity R^2: {r2:.2f} "
            f"({'single propagation path' if r2 >= _LINEAR_R2 else 'delay-spread phase structure'})")
        evidence.append(f"Interferometric delay: {tau * 1e9:.1f} ns")

    excess_delay = False
    bearing = None
    bound_ns = None
    if baseline_m is not None and baseline_m > 0 and tau is not None:
        bound_s = baseline_m / C_LIGHT
        bound_ns = bound_s * 1e9
        evidence.append(f"Far-field propagation bound for the baseline: {bound_ns:.1f} ns "
                        f"(baseline {baseline_m:g} m / c)")
        sin_theta = tau / bound_s
        if abs(sin_theta) > 1:
            excess_delay = True
            warnings.append(
                f"Measured delay {tau * 1e9:.1f} ns exceeds the {bound_ns:.1f} ns baseline/c "
                "bound: no sky propagation path can produce it -> local or instrumental origin.")
            if r2 >= _LINEAR_R2:
                warnings.append("Clean (linear) phase with excess delay suggests "
                                "instrumental path/cable delay rather than multipath.")
        else:
            bearing = float(np.degrees(np.arcsin(sin_theta)))
            evidence.append(f"Interferometric bearing: {bearing:.1f} deg off baseline broadside "
                            "(far-field direction of arrival)")
    elif baseline_m is None:
        warnings.append("No baseline length supplied: the exceeding-delay geo bound and a "
                        "sky bearing cannot be evaluated (user-supplied value required).")

    if r2 < _NONLINEAR_R2:
        verdict, conf = NEAR_FIELD, float(min(0.9, coherence))
        if not excess_delay:
            warnings.append("Phase does not fit a single propagation delay "
                            "(R^2=%.2f < %.1f) — multipath/near-field signature." % (r2, _NONLINEAR_R2))
    elif excess_delay:
        verdict, conf = NEAR_FIELD, float(min(0.9, coherence))
    elif r2 >= _LINEAR_R2:
        verdict, conf = SKY, float(min(0.9, r2))
    else:
        verdict, conf = INCONCLUSIVE, 0.3
        warnings.append("Propagation model ambiguous (linearity between "
                        f"{_NONLINEAR_R2} and {_LINEAR_R2}): verdict inconclusive.")

    return Estimate(name, verdict, None, Source.ESTIMATED, confidence=conf,
                    evidence=evidence, warnings=warnings)
