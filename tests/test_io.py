import numpy as np
import pytest
from scipy.io import wavfile

from signalscope_dsp.io import load_wav, load_raw_iq, RawIQFormat
from signalscope_dsp.common import Source


def test_load_wav_stereo_iq(tmp_path):
    fs = 8000
    t = np.arange(fs)
    left = (0.5 * np.sin(2 * np.pi * 100 * t / fs) * 32767).astype(np.int16)
    right = (0.5 * np.cos(2 * np.pi * 100 * t / fs) * 32767).astype(np.int16)
    stereo = np.stack([left, right], axis=1)
    path = tmp_path / "test.wav"
    wavfile.write(str(path), fs, stereo)

    rec = load_wav(path, stereo_mode="left_is_i_right_is_q")
    assert rec.metadata.sample_rate.source == Source.METADATA
    assert rec.metadata.sample_rate.value == fs
    assert rec.metadata.is_complex is True
    assert len(rec.samples) == fs
    assert rec.samples.dtype == np.complex64


def test_load_wav_mono_is_real(tmp_path):
    fs = 4000
    t = np.arange(fs)
    mono = (0.3 * np.sin(2 * np.pi * 50 * t / fs) * 32767).astype(np.int16)
    path = tmp_path / "mono.wav"
    wavfile.write(str(path), fs, mono)

    rec = load_wav(path)
    assert rec.metadata.is_complex is False
    assert np.allclose(rec.samples.imag, 0)


def test_load_raw_iq_interleaved_int16(tmp_path):
    n = 1000
    i = (np.sin(np.linspace(0, 10, n)) * 10000).astype(np.int16)
    q = (np.cos(np.linspace(0, 10, n)) * 10000).astype(np.int16)
    interleaved = np.empty(2 * n, dtype=np.int16)
    interleaved[0::2] = i
    interleaved[1::2] = q
    path = tmp_path / "test.iq"
    interleaved.tofile(path)

    fmt = RawIQFormat(dtype="int16", layout="interleaved", sample_rate_hz=2_000_000)
    rec = load_raw_iq(path, fmt)
    assert rec.metadata.sample_rate.source == Source.USER_SUPPLIED
    assert rec.metadata.sample_rate.value == 2_000_000
    assert len(rec.samples) == n
    assert rec.metadata.is_complex is True


def test_load_raw_iq_no_sample_rate_is_unknown(tmp_path):
    data = np.zeros(100, dtype=np.int16)
    path = tmp_path / "nosr.iq"
    data.tofile(path)
    fmt = RawIQFormat(dtype="int16", layout="interleaved")  # no sample rate given
    rec = load_raw_iq(path, fmt)
    assert rec.metadata.sample_rate.source == Source.UNKNOWN
    assert rec.metadata.sample_rate.value is None
