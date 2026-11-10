"""Interferometric origin: a sky plane wave delivers a shared single-path
signal; multipath, excess delay, and unshared noise deliver the local /
inconclusive verdicts. Also covers the 2-antenna raw-IQ frame format."""
import numpy as np

from signalscope_dsp.interferometry import interferometric_origin, SKY, NEAR_FIELD, INCONCLUSIVE
from signalscope_dsp.io import load_raw_iq, RawIQFormat
from signalscope_dsp.common import Source

FS = 5_000_000.0


def _band_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """Compact-band complex noise (shared "signal" content for both antennas)."""
    x = (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64)
    spec = np.fft.fft(x)
    drop = np.abs(np.fft.fftfreq(n, 1 / FS)) > 0.2 * FS
    spec[drop] = 0
    sig = np.fft.ifft(spec).astype(np.complex64)
    return sig / np.sqrt(np.mean(np.abs(sig) ** 2))


def _delay(sig: np.ndarray, tau_s: float) -> np.ndarray:
    """Fractional frequency-domain delay."""
    n = len(sig)
    return np.fft.ifft(np.fft.fft(sig) * np.exp(-2j * np.pi * np.fft.fftfreq(n, 1 / FS) * tau_s)).astype(np.complex64)


def _rng():
    return np.random.default_rng(42)


def test_sky_plane_wave_single_path():
    rng = _rng()
    s = _band_noise(60_000, rng)
    baseline_m, theta_deg = 300.0, 30.0
    tau = baseline_m * np.sin(np.radians(theta_deg)) / 299_792_458.0  # 500 ns
    ant0 = s + 0.4 * (rng.standard_normal(len(s)) + 1j * rng.standard_normal(len(s)))
    ant1 = _delay(s, tau) + 0.4 * (rng.standard_normal(len(s)) + 1j * rng.standard_normal(len(s)))
    est = interferometric_origin([ant0, ant1], FS, baseline_m=baseline_m)
    assert est.value == SKY
    assert est.confidence is not None and est.confidence > 0.5
    joined = " ".join(est.evidence)
    # delay sign depends on which antenna leads; magnitude and bearing matter
    import re
    ns = [float(m) for m in re.findall(r" ([\d.]+) ns", joined)]
    assert ns and abs(ns[0] - tau * 1e9) < 0.5 * tau * 1e9
    assert "30.0 deg off baseline broadside" in joined
    assert "Coherence above the 0.25 threshold" in joined
    assert est.warnings == []


def test_near_field_excess_delay_beats_baseline_bound():
    rng = _rng()
    s = _band_noise(60_000, rng)
    n1 = rng.standard_normal(60_000) + 1j * rng.standard_normal(60_000)
    n2 = rng.standard_normal(60_000) + 1j * rng.standard_normal(60_000)
    tau = 0.5e-6  # 500 ns impossible for a 40 m baseline (bound ~133 ns)
    est = interferometric_origin(
        [s + 0.4 * n1, _delay(s, tau) + 0.4 * n2], FS, baseline_m=40.0)
    assert est.value == NEAR_FIELD
    assert any("baseline/c" in w for w in est.warnings)


def test_near_field_multipath_breaks_phase_linearity():
    rng = _rng()
    s = _band_noise(60_000, rng)
    noise = rng.standard_normal(60_000) + 1j * rng.standard_normal(60_000)
    late = _delay(s, 5e-6)  # 2 phase oscillations across the signal band
    est = interferometric_origin(
        [s + 0.4 * noise, 0.6 * s + 0.5 * late + 0.4 * noise], FS, baseline_m=None)
    assert est.value == NEAR_FIELD


def test_no_shared_signal_is_inconclusive():
    rng = _rng()
    a = _band_noise(60_000, rng)
    b = _band_noise(60_000, rng)  # independent content
    est = interferometric_origin([a, b], FS, baseline_m=10.0)
    assert est.value == INCONCLUSIVE
    assert any("coherent" in w for w in est.warnings)


def test_degenerate_inputs_are_unknown():
    est = interferometric_origin([np.zeros(10, dtype=np.complex64)], FS)
    assert est.value is None and est.source == Source.UNKNOWN
    est = interferometric_origin([np.zeros(16, dtype=np.complex64),
                                  np.zeros(16, dtype=np.complex64)], FS)
    assert est.value is None and est.source == Source.UNKNOWN


def test_dual_antenna_raw_iq_frames(tmp_path):
    """interleaved IQ with channels=2: frames are I/Q per antenna, in frame
    order [I0 Q0 I1 Q1]."""
    n = 300
    idx = np.arange(n)
    ch0 = np.stack([np.sin(2 * np.pi * 50 * idx / FS).astype(np.float32) * 8000,
                    np.zeros(n, dtype=np.float32)], axis=1)
    ch1 = np.stack([np.zeros(n, dtype=np.float32),
                    np.cos(2 * np.pi * 50 * idx / FS).astype(np.float32) * 8000], axis=1)
    raw = np.concatenate([ch0, ch1], axis=1).astype(np.int16)
    raw.tofile(tmp_path / "dual.iq")

    for recorder in (load_raw_iq(tmp_path / "dual.iq",
                                 RawIQFormat(dtype="int16", layout="interleaved", channels=2,
                                             sample_rate_hz=FS)),
                     ):
        assert recorder.metadata.channel_count == 2
        assert recorder.metadata.total_samples == n
        assert np.allclose(recorder.samples.real, ch0[:, 0] / 32768, atol=1e-3)
        assert recorder.other_channels[0].imag[:5] != 0
        assert np.allclose(recorder.other_channels[0].real, 0, atol=1e-6)

    single = load_raw_iq(tmp_path / "dual.iq",
                         RawIQFormat(dtype="int16", layout="interleaved", sample_rate_hz=FS))
    assert single.metadata.channel_count == 1
    assert single.other_channels == ()
