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


def load_wav(
    path: str | Path,
    stereo_mode: StereoMode = "left_is_i_right_is_q",
    *,
    sample_offset: int = 0,
    max_samples: int | None = None,
) -> Recording:
    """Load a .wav file into the normalized complex64 representation.

    Mono files are treated as real-valued signals (Q = 0), with a warning attached
    to the metadata so downstream stages know no true quadrature data is present.

    `sample_offset` / `max_samples` bound the samples returned. PCM files are
    memory-mapped so a window does not pull the whole recording into RAM;
    `metadata.total_samples` always reports the full file length.
    """
    path = Path(path)
    try:
        fs, raw_all = wavfile.read(str(path), mmap=True)
    except (ValueError, TypeError):
        # Compressed / non-PCM WAV: scipy cannot memory-map, fall back to a full read.
        fs, raw_all = wavfile.read(str(path))

    total_samples = int(raw_all.shape[0])
    sample_offset = max(0, sample_offset)
    stop = None if max_samples is None else sample_offset + max_samples
    raw = raw_all[sample_offset:stop]
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
        duration_seconds=total_samples / fs if fs else None,
        total_samples=total_samples,
        extra={
            "stereo_mode": stereo_mode,
            "original_dtype": orig_dtype,
            "loaded_samples": len(complex_samples),
        },
    )
    if metadata.center_frequency is None:
        metadata.extra["center_frequency_warning"] = (
            "No RF center frequency in WAV metadata. Supply one manually if known; "
            "otherwise spectral plots will be shown baseband (relative to 0 Hz)."
        )

    rec = Recording(samples=complex_samples, metadata=metadata, source_path=str(path))
    rec.metadata.extra["warnings"] = warnings
    return rec
