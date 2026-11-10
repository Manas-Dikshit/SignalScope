"""Space-medium & celestial context output: scintillation (S4), Earth-rotation
Doppler-bound drift verdict, equivalent acceleration, and hydrogen-line radial
velocity."""
from __future__ import annotations

import numpy as np
import pytest

from signalscope_dsp.features import analyze_space_medium

FS = 8000.0
HYDROGEN_LINE_HZ = 1_420_405_751.0


def _tone(seconds: float, freq: float = 1000.0, fs: float = FS) -> np.ndarray:
    t = np.arange(int(seconds * fs)) / fs
    return np.exp(1j * 2 * np.pi * freq * t).astype(np.complex128)


def _chirp(seconds: float, drift_hz_per_s: float, freq: float = 1000.0,
           fs: float = FS) -> np.ndarray:
    t = np.arange(int(seconds * fs)) / fs
    phase = 2 * np.pi * (freq * t + 0.5 * drift_hz_per_s * t**2)
    return np.exp(1j * phase).astype(np.complex128)


def test_stable_tone_has_no_scintillation():
    out = analyze_space_medium(_tone(10.0), FS)
    assert out.scintillation_index_s4.value is not None
    assert out.scintillation_index_s4.value < 0.05
    assert "Classification: stable" in " ".join(out.scintillation_index_s4.evidence)
    assert out.fading_rate_hz.value is not None and out.fading_rate_hz.value < 0.5


def test_faded_tone_shows_scintillation():
    t = np.arange(int(10.0 * FS)) / FS
    faded = _tone(10.0) * (1.0 + 0.6 * np.sin(2 * np.pi * 2.0 * t))
    out = analyze_space_medium(faded, FS)
    assert out.scintillation_index_s4.value > 0.3
    assert "scintillation" in " ".join(out.scintillation_index_s4.evidence)


def test_slow_drift_is_celestial_consistent_fast_drift_exceeds_bound():
    center = 10e9  # X-band, where the celestial bound is measurable in short windows
    bound = (0.0339 / 299_792_458.0) * (center + 1000.0)
    # fs=2000 gives fine STFT bins so the 0.5 Hz/s ridge is trackable
    slow = analyze_space_medium(_chirp(20.0, 0.5, fs=2000.0), 2000.0, center_frequency_hz=center)
    fast = analyze_space_medium(_chirp(20.0, 50.0, fs=2000.0), 2000.0, center_frequency_hz=center)

    assert slow.drift_celestial_verdict.value == "celestial_consistent"
    assert slow.earth_rotation_doppler_bound.value == pytest.approx(bound, rel=1e-3)
    assert fast.drift_celestial_verdict.value == "exceeds_celestial_bound"
    assert fast.equivalent_acceleration.value is not None
    # a = c * drift / f_rf
    expected_a = 299_792_458.0 * 50.0 / (center + 1000.0)
    assert fast.equivalent_acceleration.value == pytest.approx(expected_a, rel=1e-3)


def test_without_center_frequency_verdict_is_unknown():
    out = analyze_space_medium(_chirp(20.0, 50.0), FS)
    assert out.earth_rotation_doppler_bound.value is None
    assert out.drift_celestial_verdict.value == "unknown"
    assert out.equivalent_acceleration.value is None


def test_hydrogen_line_velocity_only_near_1420_mhz():
    near = analyze_space_medium(_tone(10.0), FS, center_frequency_hz=HYDROGEN_LINE_HZ)
    assert near.hydrogen_line_radial_velocity is not None
    # +1 kHz baseband offset -> v = c * 1000 / f_rest, ~0.2114 km/s
    assert near.hydrogen_line_radial_velocity.value == pytest.approx(0.2114, abs=0.01)
    assert near.hydrogen_line_radial_velocity.source.value == "hypothesis"

    far = analyze_space_medium(_tone(10.0), FS, center_frequency_hz=100_000_000.0)
    assert far.hydrogen_line_radial_velocity is None


def test_short_window_is_honest():
    out = analyze_space_medium(_tone(0.01), FS)
    assert out.scintillation_index_s4.value is None
    assert any("too short" in w.lower() for w in out.scintillation_index_s4.warnings)
