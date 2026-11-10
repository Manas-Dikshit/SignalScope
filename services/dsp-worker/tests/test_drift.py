"""Frequency drift rate: known chirp recovers the true slope; noise and
degenerate inputs get honest low-confidence / unknown answers."""
import numpy as np

from signalscope_dsp.features import estimate_frequency_drift_rate
from signalscope_dsp.common import Source


def _chirp(fs: float, drift_hz_per_s: float, t_len: float = 4.0) -> np.ndarray:
    t = np.arange(int(fs * t_len)) / fs
    phase = 2 * np.pi * (1000.0 * t + 0.5 * drift_hz_per_s * t ** 2)
    return np.exp(1j * phase).astype(np.complex64)


def test_known_chirp_recovers_drift_rate():
    fs = 8192.0
    true_slope = 500.0  # Hz/s
    est = estimate_frequency_drift_rate(_chirp(fs, true_slope), fs)
    assert est.value is not None
    assert abs(est.value - true_slope) < 0.05 * true_slope
    assert est.source == Source.ESTIMATED
    assert est.confidence is not None and est.confidence > 0.5
    assert est.warnings == []


def test_zero_drift_stays_near_zero():
    fs = 8192.0
    est = estimate_frequency_drift_rate(_chirp(fs, 0.0), fs)
    assert est.value is not None
    assert abs(est.value) < 50.0


def test_noise_ridge_flagged_not_meaningful():
    fs = 8192.0
    rng = np.random.default_rng(7)
    noise = (rng.standard_normal(int(fs * 2)) + 1j * rng.standard_normal(int(fs * 2))).astype(np.complex64)
    est = estimate_frequency_drift_rate(noise, fs)
    assert est.warnings, "noise ridge should be flagged as unstable"


def test_degenerate_inputs_are_unknown():
    fs = 8192.0
    est = estimate_frequency_drift_rate(np.array([], dtype=np.complex64), fs)
    assert est.value is None and est.source == Source.UNKNOWN
    est = estimate_frequency_drift_rate(np.zeros(16, dtype=np.complex64), fs)
    assert est.value is None and est.source == Source.UNKNOWN
