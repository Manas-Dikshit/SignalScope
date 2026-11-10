from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import signal as sp_signal

from ..common import Estimate, Source


def compute_psd(samples: np.ndarray, sample_rate: float, fft_size: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    """Welch PSD. Returns (freqs_hz, psd_db)."""
    nperseg = min(fft_size, len(samples))
    if nperseg < 8:
        nperseg = len(samples)
    freqs, pxx = sp_signal.welch(samples, fs=sample_rate, nperseg=nperseg, return_onesided=False)
    freqs = np.fft.fftshift(freqs)
    pxx = np.fft.fftshift(pxx)
    pxx_db = 10 * np.log10(pxx + 1e-20)
    return freqs, pxx_db


def compute_waterfall(samples: np.ndarray, sample_rate: float, fft_size: int = 1024, overlap: float = 0.5,
                       window: str = "hann") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (freqs_hz, times_s, spectrogram_db) shape (n_freq, n_time)."""
    noverlap = int(fft_size * overlap)
    freqs, times, sxx = sp_signal.spectrogram(
        samples, fs=sample_rate, window=window, nperseg=fft_size, noverlap=noverlap,
        return_onesided=False, mode="magnitude",
    )
    freqs = np.fft.fftshift(freqs)
    sxx = np.fft.fftshift(sxx, axes=0)
    sxx_db = 20 * np.log10(sxx + 1e-20)
    return freqs, times, sxx_db


def spectral_centroid(freqs: np.ndarray, psd_linear: np.ndarray) -> float:
    weights = psd_linear - psd_linear.min()
    total = np.sum(weights)
    if total <= 0:
        return 0.0
    return float(np.sum(freqs * weights) / total)


def spectral_flatness(psd_linear: np.ndarray) -> float:
    psd_linear = np.maximum(psd_linear, 1e-20)
    geo_mean = np.exp(np.mean(np.log(psd_linear)))
    arith_mean = np.mean(psd_linear)
    return float(geo_mean / arith_mean) if arith_mean > 0 else 0.0


def crest_factor(samples: np.ndarray) -> float:
    mag = np.abs(samples)
    rms = np.sqrt(np.mean(mag ** 2))
    if rms == 0:
        return 0.0
    return float(np.max(mag) / rms)


def zero_crossing_rate(samples: np.ndarray) -> float:
    real = samples.real
    crossings = np.sum(np.abs(np.diff(np.sign(real))) > 0)
    return float(crossings) / max(len(real) - 1, 1)


def instantaneous_phase(samples: np.ndarray) -> np.ndarray:
    return np.unwrap(np.angle(samples))


def instantaneous_frequency(samples: np.ndarray, sample_rate: float) -> np.ndarray:
    phase = instantaneous_phase(samples)
    return np.diff(phase) * sample_rate / (2 * np.pi)


def occupied_bandwidth(freqs: np.ndarray, psd_db: np.ndarray, power_fraction: float = 0.99) -> tuple[float, float]:
    """Returns (low_hz, high_hz) containing power_fraction of total power."""
    psd_linear = 10 ** (psd_db / 10)
    total = np.sum(psd_linear)
    if total <= 0:
        return float(freqs[0]), float(freqs[-1])
    cumulative = np.cumsum(psd_linear) / total
    low_idx = int(np.searchsorted(cumulative, (1 - power_fraction) / 2))
    high_idx = int(np.searchsorted(cumulative, 1 - (1 - power_fraction) / 2))
    low_idx = min(max(low_idx, 0), len(freqs) - 1)
    high_idx = min(max(high_idx, 0), len(freqs) - 1)
    return float(freqs[low_idx]), float(freqs[high_idx])


def estimate_snr_db(samples: np.ndarray, sample_rate: float, fft_size: int = 4096) -> float:
    """Rough SNR estimate: treats the strongest contiguous spectral region as signal
    and the noise floor (median of the rest) as noise. This is an ESTIMATE, not a
    calibrated measurement."""
    freqs, psd_db = compute_psd(samples, sample_rate, fft_size)
    noise_floor_db = float(np.median(psd_db))
    peak_db = float(np.max(psd_db))
    return peak_db - noise_floor_db


def estimate_frequency_drift_rate(samples: np.ndarray, sample_rate: float, fft_size: int = 1024) -> Estimate:
    """Frequency drift rate of the dominant signal component, in Hz/s.

    Tracks the per-frame argmax frequency of the STFT (the frequency ridge) and
    fits a line over time; the slope is the drift rate. Confidence is tied to
    the linearity (R^2) of the ridge so noise or wideband signals get an honest
    low-confidence answer instead of a reassuring number."""
    name = "frequency_drift_rate"
    if len(samples) < 8 or sample_rate <= 0:
        return Estimate(name, None, "Hz/s", Source.UNKNOWN)

    nperseg = min(fft_size, len(samples))
    freqs, times, sxx = sp_signal.spectrogram(
        samples, fs=sample_rate, window="hann", nperseg=nperseg, noverlap=nperseg * 3 // 4,
        return_onesided=False, mode="magnitude",
    )
    freqs = np.fft.fftshift(freqs)
    sxx = np.fft.fftshift(sxx, axes=0)
    if sxx.shape[1] < 2:
        return Estimate(name, None, "Hz/s", Source.UNKNOWN,
                        warnings=["Too few frames in the recording for drift estimation."])

    ridge = freqs[np.argmax(sxx, axis=0)]
    t = times - times[0]
    if float(np.var(t)) <= 0:
        return Estimate(name, None, "Hz/s", Source.UNKNOWN,
                        warnings=["Only one distinct frame; drift rate undefined."])

    t_c = t - t.mean()
    r_c = ridge - ridge.mean()
    slope = float(np.dot(t_c, r_c) / np.dot(t_c, t_c))
    residual = float(np.sum((r_c - slope * t_c) ** 2))
    total = float(np.sum(r_c ** 2))
    r2 = 1.0 - residual / total if total > 0 else 1.0

    warnings = []
    if r2 < 0.5:
        warnings.append(f"Frequency ridge is unstable (R^2={r2:.2f}); drift rate may not be meaningful "
                        "for noisy or wideband signals.")
    return Estimate(
        name=name, value=slope, unit="Hz/s", source=Source.ESTIMATED,
        confidence=float(min(0.9, max(0.0, r2))),
        evidence=["Per-frame argmax of STFT magnitude, least-squares fit of ridge vs time"],
        warnings=warnings,
    )


@dataclass
class SpectralFeatures:
    occupied_bandwidth_hz: Estimate
    peak_frequency_hz: Estimate
    spectral_centroid_hz: Estimate
    spectral_flatness: Estimate
    crest_factor: Estimate
    zero_crossing_rate: Estimate
    snr_db: Estimate
    frequency_drift_rate: Estimate
    warnings: list[str] = field(default_factory=list)


def extract_spectral_features(samples: np.ndarray, sample_rate: float, fft_size: int = 4096) -> SpectralFeatures:
    freqs, psd_db = compute_psd(samples, sample_rate, fft_size)
    psd_linear = 10 ** (psd_db / 10)

    low_hz, high_hz = occupied_bandwidth(freqs, psd_db)
    obw = high_hz - low_hz
    peak_freq = float(freqs[np.argmax(psd_db)])
    centroid = spectral_centroid(freqs, psd_linear)
    flatness = spectral_flatness(psd_linear)
    crest = crest_factor(samples)
    zcr = zero_crossing_rate(samples)
    snr = estimate_snr_db(samples, sample_rate, fft_size)
    drift = estimate_frequency_drift_rate(samples, sample_rate)

    return SpectralFeatures(
        occupied_bandwidth_hz=Estimate("occupied_bandwidth", obw, "Hz", Source.ESTIMATED, confidence=0.6,
                                        evidence=["99% power-containment bandwidth from Welch PSD"]),
        peak_frequency_hz=Estimate("peak_frequency", peak_freq, "Hz", Source.MEASURED,
                                    evidence=["argmax of PSD"]),
        spectral_centroid_hz=Estimate("spectral_centroid", centroid, "Hz", Source.MEASURED),
        spectral_flatness=Estimate("spectral_flatness", flatness, None, Source.MEASURED,
                                    evidence=["Wiener entropy: geometric mean / arithmetic mean of PSD"]),
        crest_factor=Estimate("crest_factor", crest, None, Source.MEASURED),
        zero_crossing_rate=Estimate("zero_crossing_rate", zcr, None, Source.MEASURED),
        snr_db=Estimate("snr", snr, "dB", Source.ESTIMATED, confidence=0.5,
                         evidence=["peak PSD minus median PSD (noise-floor proxy)"],
                         warnings=["Rough estimate; assumes noise dominates the spectral median."]),
        frequency_drift_rate=drift,
    )
