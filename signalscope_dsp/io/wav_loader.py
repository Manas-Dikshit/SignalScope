from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from scipy.io import wavfile

from ..common import Estimate, Recording, RecordingMetadata, Source

StereoMode = Literal["left_is_i_right_is_q", "left_only", "right_only", "mono_mix"]


def _to_float(samples: np.ndarray) -> np.ndarray:
    """Normalize any PCM/float WAV dtype to float32 in [-1, 1]."""
    if np.issubdtype(samples.dtype, np.floating):
        return samples.astype(np.float32)
    if samples.dtype == np.uint8:
        # 8-bit WAV is unsigned, centered at 128
        return (samples.astype(np.float32) - 128.0) / 128.0
    info = np.iinfo(samples.dtype)
    return samples.astype(np.float32) / max(abs(info.min), info.max)


def load_wav(path: str | Path, stereo_mode: StereoMode = "left_is_i_right_is_q") -> Recording:
    """Load a .wav file into the normalized complex64 representation.

    Mono files are treated as real-valued signals (Q = 0), with a warning attached
    to the metadata so downstream stages know no true quadrature data is present.
    """
    path = Path(path)
    fs, raw = wavfile.read(str(path))
    orig_dtype = str(raw.dtype)
    warnings: list[str] = []

    if raw.ndim == 1:
        channels = 1
        data = _to_float(raw)
        i = data
        q = np.zeros_like(data)
        is_complex = False
        warnings.append(
            "Mono WAV file: no true quadrature data present. Treated as a "
            "real-valued signal (Q forced to zero)."
        )
    else:
        channels = raw.shape[1]
        if channels < 2:
            raise ValueError(f"Unexpected WAV channel layout: shape={raw.shape}")
        left = _to_float(raw[:, 0])
        right = _to_float(raw[:, 1])
        if stereo_mode == "left_is_i_right_is_q":
            i, q, is_complex = left, right, True
        elif stereo_mode == "left_only":
            i, q, is_complex = left, np.zeros_like(left), False
            warnings.append("Using left channel only as a real-valued signal.")
        elif stereo_mode == "right_only":
            i, q, is_complex = right, np.zeros_like(right), False
            warnings.append("Using right channel only as a real-valued signal.")
        elif stereo_mode == "mono_mix":
            mixed = (left + right) / 2.0
            i, q, is_complex = mixed, np.zeros_like(mixed), False
            warnings.append("Channels averaged into a single real-valued signal.")
        else:
            raise ValueError(f"Unknown stereo_mode: {stereo_mode}")
        if channels > 2:
            warnings.append(f"WAV has {channels} channels; only the first two were used.")

    complex_samples = (i + 1j * q).astype(np.complex64)

    sample_rate_est = Estimate(
        name="sample_rate",
        value=float(fs),
        unit="Hz",
        source=Source.METADATA,
        evidence=["Read directly from WAV RIFF header."],
    )

    metadata = RecordingMetadata(
        sample_rate=sample_rate_est,
        center_frequency=None,  # WAV headers never carry RF center frequency
        is_complex=is_complex,
        channel_count=channels,
        sample_dtype=orig_dtype,
        duration_seconds=len(complex_samples) / fs if fs else None,
        total_samples=len(complex_samples),
        extra={"stereo_mode": stereo_mode, "original_dtype": orig_dtype},
    )
    if metadata.center_frequency is None:
        metadata.extra["center_frequency_warning"] = (
            "No RF center frequency in WAV metadata. Supply one manually if known; "
            "otherwise spectral plots will be shown baseband (relative to 0 Hz)."
        )

    rec = Recording(samples=complex_samples, metadata=metadata, source_path=str(path))
    rec.metadata.extra["warnings"] = warnings
    return rec
