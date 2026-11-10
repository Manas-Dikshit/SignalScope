"""Space medium & celestial context from a recorded signal.

One deep-analysis output that answers questions about space rather than
about the transmitter's data content:

- **Scintillation index (S4)** — amplitude-fading depth of the received
  power envelope. Ionised plasma (ionosphere, solar wind) and multipath
  modulate the received power; the S4 index is the standard GNSS-style
  scintillation metric, reported here as a space-weather indicator.
- **Drift vs the Earth-rotation Doppler bound** — a source fixed to the
  sky cannot Doppler-shift faster than the Earth's rotation at the observing
  frequency (~1.55e-6 * f_rf Hz/s at rise/set). Drift beyond that bound is
  instrumental or terrestrial; drift within it is consistent with celestial
  sky motion.
- **Equivalent line-of-sight acceleration** — the drift rate expressed as
  the Doppler acceleration of the source, in m/s^2.
- **Hydrogen-line radial velocity** — when the recording is tuned near the
  1420.405751 MHz hydrogen line, the measured RF offset converts to a
  radial velocity in km/s (a hypothesis, since the tuner offset may be
  instrumental).

Everything is an estimate over the analysed window. Without a calibrated
antenna and a known Tsys these numbers cannot be absolute astronomy; they
are honest, explainable context about the medium and the source's motion.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..common import Estimate, Source
from .spectral import compute_psd, estimate_frequency_drift_rate

C_M_S = 299_792_458.0
# Maximum line-of-sight acceleration a sky-fixed source can have from Earth
# rotation: omega^2 * R_planet at the equator (~0.034 m/s^2). The resulting
# Doppler *drift-rate* bound is (0.034 * f_rf / c) ~ 0.16 Hz/s at the 21 cm line.
EARTH_ROT_ACCEL_M_S2 = 0.0339
HYDROGEN_LINE_HZ = 1_420_405_751.0  # 21 cm neutral hydrogen line
HYDROGEN_WINDOW_HZ = 2.7e6  # +/- ~570 km/s around the line

S4_STABLE = 0.1
S4_STRONG = 0.5
DRIFT_TOLERANCE = 1.5  # allow multipath/refraction slack before exceeding


def _scintillation_class(s4: float) -> str:
    if s4 < S4_STABLE:
        return "stable"
    if s4 <= S4_STRONG:
        return "moderate_scintillation"
    return "strong_scintillation"


@dataclass
class SpaceMediumResult:
    scintillation_index_s4: Estimate
    fading_rate_hz: Estimate
    drift_celestial_verdict: Estimate
    earth_rotation_doppler_bound: Estimate
    equivalent_acceleration: Estimate
    hydrogen_line_radial_velocity: Estimate | None
    warnings: list[str] = field(default_factory=list)

    @property
    def estimates(self) -> list[Estimate]:
        out = [
            self.scintillation_index_s4,
            self.fading_rate_hz,
            self.drift_celestial_verdict,
            self.earth_rotation_doppler_bound,
            self.equivalent_acceleration,
        ]
        if self.hydrogen_line_radial_velocity is not None:
            out.append(self.hydrogen_line_radial_velocity)
        return out


def analyze_space_medium(
    samples: np.ndarray,
    sample_rate: float,
    center_frequency_hz: float | None = None,
    smoothing_ms: float = 20.0,
) -> SpaceMediumResult:
    work = np.asarray(samples)
    warnings: list[str] = []

    # --- Envelope statistics (scintillation) --------------------------------
    power = np.abs(work) ** 2
    win = max(1, int(sample_rate * smoothing_ms / 1000.0))
    kernel = np.ones(win) / win
    smoothed = np.convolve(power, kernel, mode="same")
    mean_power = float(np.mean(smoothed))

    if work.size < max(64, 10 * win) or not sample_rate or sample_rate <= 0:
        s4_est = Estimate("scintillation_index_s4", None, None, Source.UNKNOWN,
                          warnings=["Window too short for scintillation analysis."])
        fade_est = Estimate("fading_rate", None, "Hz", Source.UNKNOWN,
                            warnings=["Window too short for scintillation analysis."])
        drift_est = Estimate("frequency_drift_rate", None, "Hz/s", Source.UNKNOWN)
    elif mean_power <= 0:
        s4_est = Estimate("scintillation_index_s4", None, None, Source.UNKNOWN,
                          warnings=["Zero mean power; scintillation undefined."])
        fade_est = Estimate("fading_rate", None, "Hz", Source.UNKNOWN,
                            warnings=["Zero mean power; fading rate undefined."])
        drift_est = estimate_frequency_drift_rate(work, sample_rate)
    else:
        s4 = float(np.std(smoothed) / mean_power)
        duration_s = work.size / float(sample_rate)
        crossings = int(np.sum(np.abs(np.diff(np.sign(smoothed - mean_power))) > 0))
        fade_rate = crossings / (2.0 * duration_s) if duration_s > 0 else None
        s4_est = Estimate(
            name="scintillation_index_s4",
            value=round(s4, 4),
            unit=None,
            source=Source.ESTIMATED,
            confidence=0.7 if duration_s >= 1.0 else 0.4,
            evidence=[
                f"Std/mean of the {smoothing_ms:.0f} ms-smoothed power envelope (S4)",
                f"Classification: {_scintillation_class(s4)}",
                "S4 < 0.1 stable; 0.1-0.5 moderate; > 0.5 strong scintillation",
            ],
            warnings=(["Short window: ionospheric and multipath fading cannot be separated."]
                      if duration_s < 10.0 else []),
        )
        fade_est = Estimate(
            name="fading_rate",
            value=round(fade_rate, 4) if fade_rate is not None else None,
            unit="Hz",
            source=Source.ESTIMATED,
            confidence=s4_est.confidence,
            evidence=["Mean-crossing rate of the power envelope / 2 (fade events per second)"],
        )
        drift_est = estimate_frequency_drift_rate(work, sample_rate)

    # --- Doppler physics (needs an absolute RF frequency) -------------------
    f_rf: float | None = None
    if center_frequency_hz:
        freqs, psd_db = compute_psd(work, sample_rate, fft_size=1024)
        peak_baseband = float(freqs[int(np.argmax(psd_db))])
        f_rf = float(center_frequency_hz) + peak_baseband

    bound_hz_s = (EARTH_ROT_ACCEL_M_S2 / C_M_S) * f_rf if f_rf else None
    bound_est = Estimate(
        name="earth_rotation_doppler_bound",
        value=round(bound_hz_s, 6) if bound_hz_s else None,
        unit="Hz/s",
        source=Source.ESTIMATED if bound_hz_s else Source.UNKNOWN,
        confidence=0.9 if bound_hz_s else None,
        evidence=(["Max Doppler drift rate a sky-fixed source can show from Earth "
                   f"rotation: (omega^2*R) * f_rf / c at f_rf = {f_rf:,.0f} Hz"]
                  if bound_hz_s else
                  ["No centre frequency metadata: absolute RF frequency unknown, "
                   "so the celestial Doppler bound cannot be evaluated."]),
    )

    drift = drift_est.value
    if drift is None or bound_hz_s is None:
        verdict = "unknown"
        verdict_conf: float | None = None
        verdict_evidence = [
            f"Measured drift: {'%.4g Hz/s' % drift if drift is not None else 'unknown'}",
            bound_est.evidence[0],
        ]
    else:
        if abs(drift) <= DRIFT_TOLERANCE * bound_hz_s:
            verdict = "celestial_consistent"
            verdict_evidence = [
                f"Measured drift {drift:.4g} Hz/s is within the Earth-rotation "
                f"Doppler bound {bound_hz_s:.4g} Hz/s (x{DRIFT_TOLERANCE} tolerance): "
                "consistent with celestial sky motion.",
            ]
        else:
            verdict = "exceeds_celestial_bound"
            verdict_evidence = [
                f"Measured drift {drift:.4g} Hz/s exceeds the Earth-rotation Doppler "
                f"bound {bound_hz_s:.4g} Hz/s (x{DRIFT_TOLERANCE} tolerance): "
                "instrumental or terrestrial origin is more likely.",
            ]
        verdict_conf = min(drift_est.confidence or 0.0, 0.9)

    acceleration = (C_M_S * drift / f_rf) if (drift is not None and f_rf) else None
    accel_est = Estimate(
        name="equivalent_line_of_sight_acceleration",
        value=round(acceleration, 6) if acceleration is not None else None,
        unit="m/s^2",
        source=Source.ESTIMATED if acceleration is not None else Source.UNKNOWN,
        confidence=verdict_conf,
        evidence=(["a = c * (df/dt) / f_rf: the Doppler acceleration the source's "
                   "line-of-sight motion would produce"]
                  if acceleration is not None else
                  ["Needs both a drift rate and an absolute RF frequency."]),
    )

    verdict_est = Estimate(
        name="drift_celestial_verdict",
        value=verdict,
        unit=None,
        source=Source.ESTIMATED if verdict != "unknown" else Source.UNKNOWN,
        confidence=verdict_conf,
        evidence=verdict_evidence,
    )

    # --- Hydrogen-line radial velocity (only when tuned near the line) ------
    hi_velocity: Estimate | None = None
    if f_rf and center_frequency_hz and abs(center_frequency_hz - HYDROGEN_LINE_HZ) <= HYDROGEN_WINDOW_HZ:
        velocity_kmps = C_M_S * (f_rf - HYDROGEN_LINE_HZ) / HYDROGEN_LINE_HZ / 1000.0
        hi_velocity = Estimate(
            name="hydrogen_line_radial_velocity",
            value=round(velocity_kmps, 4),
            unit="km/s",
            source=Source.HYPOTHESIS,
            confidence=0.4,
            evidence=[
                f"Measured RF {f_rf:,.0f} Hz vs the 1420.405751 MHz hydrogen line",
                "v = c * (f_measured - f_rest) / f_rest",
                "Hypothesis: assumes the signal is the hydrogen line; tuner offset "
                "could produce the same shift.",
            ],
        )

    return SpaceMediumResult(
        scintillation_index_s4=s4_est,
        fading_rate_hz=fade_est,
        drift_celestial_verdict=verdict_est,
        earth_rotation_doppler_bound=bound_est,
        equivalent_acceleration=accel_est,
        hydrogen_line_radial_velocity=hi_velocity,
        warnings=warnings,
    )
