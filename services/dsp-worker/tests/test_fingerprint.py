"""Rare-signal fingerprint tests.

The fingerprint drives a nearest-neighbour gallery. These tests pin the two
properties the UI depends on: the same emitter family should land close, and a
spectrally different signal should land beyond the "rare candidate" threshold.
"""
import numpy as np
import pytest

from signalscope_dsp.fingerprint import (
    DEFAULT_RARE_DISTANCE_THRESHOLD,
    FINGERPRINT_VERSION,
    compute_fingerprint,
    fingerprint_distance,
)
from signalscope_dsp.preprocessing import ConditioningConfig, condition_signal
from signalscope_dsp.synth.generator import SynthConfig, generate_signal

SAMPLE_RATE = 200_000.0


def _condition(samples: np.ndarray) -> np.ndarray:
    return condition_signal(
        samples,
        SAMPLE_RATE,
        ConditioningConfig(remove_dc_offset=True, normalize=True),
    ).samples


def _fingerprint(modulation: str, seed: int = 1, **overrides):
    cfg = SynthConfig(
        modulation=modulation,
        seed=seed,
        sample_rate_hz=SAMPLE_RATE,
        **overrides,
    )
    return compute_fingerprint(_condition(generate_signal(cfg).samples), SAMPLE_RATE)


def test_fingerprint_is_deterministic():
    a = _fingerprint("qpsk", seed=5)
    b = _fingerprint("qpsk", seed=5)
    assert a.version == FINGERPRINT_VERSION
    assert a.vector == b.vector
    assert a.dimensions == len(a.vector) == len(a.embedding) + len(a.features)
    assert fingerprint_distance(a, b) == pytest.approx(0.0, abs=1e-9)


def test_same_emitter_family_is_close():
    a = _fingerprint("qpsk", seed=1)
    b = _fingerprint("qpsk", seed=9)
    distance = fingerprint_distance(a, b)
    assert distance < DEFAULT_RARE_DISTANCE_THRESHOLD / 4


def test_spectrally_different_signal_is_a_rare_candidate():
    reference = _fingerprint("qpsk", seed=1)

    t = np.arange(40_000) / SAMPLE_RATE
    # Linear chirp sweeping most of the band: a deliberately out-of-gallery signal.
    chirp = np.exp(1j * 2 * np.pi * np.linspace(-80_000, 80_000, 40_000) * t)
    chirp = _condition(chirp.astype(np.complex64))
    outlier = compute_fingerprint(chirp, SAMPLE_RATE)

    assert fingerprint_distance(reference, outlier) > DEFAULT_RARE_DISTANCE_THRESHOLD


def test_short_window_is_empty_and_honest():
    fp = compute_fingerprint(np.ones(8, dtype=np.complex64), SAMPLE_RATE)
    assert all(value == 0.0 for value in fp.vector)
    assert fp.features["spectral_flatness"] is None
    assert fp.warnings


def test_distance_rejects_mismatched_dimensions():
    with pytest.raises(ValueError):
        fingerprint_distance([1.0, 0.0], [1.0, 0.0, 0.0])
