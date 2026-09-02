from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as sp_signal


def remove_dc(samples: np.ndarray) -> np.ndarray:
    return samples - np.mean(samples)


def normalize_amplitude(samples: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(samples))
    if peak == 0:
        return samples
    return samples / peak


def correct_iq_imbalance(samples: np.ndarray, amplitude_ratio: float = 1.0, phase_error_rad: float = 0.0) -> np.ndarray:
    """Apply a simple gain/phase correction. Only meaningful if calibration values
    are known/measured; defaults are a no-op."""
    i = samples.real
    q = samples.imag
    q_corrected = (q - i * np.sin(phase_error_rad)) / (amplitude_ratio * np.cos(phase_error_rad))
    return (i + 1j * q_corrected).astype(np.complex64)


def estimate_coarse_frequency_offset(samples: np.ndarray, sample_rate: float, fft_size: int = 4096) -> float:
    """Coarse offset estimate: peak of the FFT magnitude, useful for signals with a
    strong unmodulated or narrowband carrier component. This is a rough estimate
    (Source.ESTIMATED upstream), not an exact measurement."""
    n = min(fft_size, len(samples))
    if n == 0:
        return 0.0
    windowed = samples[:n] * np.hanning(n)
    spectrum = np.fft.fftshift(np.fft.fft(windowed))
    freqs = np.fft.fftshift(np.fft.fftfreq(n, d=1.0 / sample_rate))
    peak_idx = np.argmax(np.abs(spectrum))
    return float(freqs[peak_idx])


def shift_frequency(samples: np.ndarray, sample_rate: float, shift_hz: float) -> np.ndarray:
    n = len(samples)
    t = np.arange(n) / sample_rate
    return (samples * np.exp(-1j * 2 * np.pi * shift_hz * t)).astype(np.complex64)


def bandpass_filter(samples: np.ndarray, sample_rate: float, low_hz: float, high_hz: float, order: int = 5) -> np.ndarray:
    nyq = sample_rate / 2.0
    low = max(low_hz / nyq, 1e-6)
    high = min(high_hz / nyq, 0.999999)
    if low >= high:
        raise ValueError("low_hz must be less than high_hz within Nyquist range")
    sos = sp_signal.butter(order, [low, high], btype="bandpass", output="sos")
    return sp_signal.sosfiltfilt(sos, samples).astype(np.complex64)


def lowpass_filter(samples: np.ndarray, sample_rate: float, cutoff_hz: float, order: int = 5) -> np.ndarray:
    nyq = sample_rate / 2.0
    cutoff = min(cutoff_hz / nyq, 0.999999)
    sos = sp_signal.butter(order, cutoff, btype="lowpass", output="sos")
    return sp_signal.sosfiltfilt(sos, samples).astype(np.complex64)


@dataclass
class ConditioningConfig:
    remove_dc_offset: bool = True
    normalize: bool = True
    coarse_freq_correction: bool = False
    iq_imbalance_correction: bool = False
    amplitude_ratio: float = 1.0
    phase_error_rad: float = 0.0


@dataclass
class ConditioningResult:
    samples: np.ndarray
    applied_steps: list[str]
    coarse_freq_offset_hz: float | None = None


def condition_signal(samples: np.ndarray, sample_rate: float, cfg: ConditioningConfig) -> ConditioningResult:
    out = samples.astype(np.complex64).copy()
    applied: list[str] = []

    if cfg.remove_dc_offset:
        out = remove_dc(out)
        applied.append("dc_removal")

    if cfg.iq_imbalance_correction:
        out = correct_iq_imbalance(out, cfg.amplitude_ratio, cfg.phase_error_rad)
        applied.append("iq_imbalance_correction")

    freq_offset = None
    if cfg.coarse_freq_correction and sample_rate:
        freq_offset = estimate_coarse_frequency_offset(out, sample_rate)
        out = shift_frequency(out, sample_rate, freq_offset)
        applied.append(f"coarse_freq_correction(shift={freq_offset:.1f}Hz)")

    if cfg.normalize:
        out = normalize_amplitude(out)
        applied.append("amplitude_normalization")

    return ConditioningResult(samples=out, applied_steps=applied, coarse_freq_offset_hz=freq_offset)
