from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import numpy as np

from ..common import Estimate, Recording, RecordingMetadata, Source

DTYPE_MAP = {
    "int8": np.int8,
    "uint8": np.uint8,
    "int16": np.int16,
    "uint16": np.uint16,
    "int32": np.int32,
    "float32": np.float32,
    "float64": np.float64,
}


@dataclass
class RawIQFormat:
    """Every field the spec requires the user to be able to set explicitly.

    A raw .IQ file is not self-describing, so nothing here is guessed silently:
    if the caller doesn't supply sample_rate, it is recorded as UNKNOWN, not
    inferred.
    """

    dtype: str = "int16"
    layout: Literal["interleaved", "separate_iq", "real_only"] = "interleaved"
    endian: Literal["little", "big"] = "little"
    signed_offset: bool = True  # for unsigned formats, whether to subtract the midpoint
    sample_rate_hz: Optional[float] = None
    center_frequency_hz: Optional[float] = None


def _read_typed(
    path: Path,
    dtype: str,
    endian: str,
    *,
    count: int = -1,
    offset: int = 0,
) -> np.ndarray:
    base = np.dtype(DTYPE_MAP[dtype])
    byteorder = "<" if endian == "little" else ">"
    typed = base.newbyteorder(byteorder) if base.itemsize > 1 else base
    return np.fromfile(path, dtype=typed, count=count, offset=offset)


def _total_scalars(path: Path, dtype: str) -> int:
    itemsize = np.dtype(DTYPE_MAP[dtype]).itemsize
    return path.stat().st_size // itemsize


def load_raw_iq(
    path: str | Path,
    fmt: RawIQFormat,
    *,
    sample_offset: int = 0,
    max_samples: int | None = None,
) -> Recording:
    """Load raw I/Q, optionally reading only a bounded window.

    `sample_offset` and `max_samples` are expressed in complex samples. They
    let interactive endpoints avoid pulling a multi-hundred-MB recording into
    memory; `metadata.total_samples` still reports the full file length so ROI
    math stays correct.
    """
    path = Path(path)
    sample_offset = max(0, sample_offset)
    total_scalars = _total_scalars(path, fmt.dtype)
    scalar_offset = 0
    count = -1

    warnings: list[str] = []

    if fmt.layout == "interleaved":
        if total_scalars % 2 != 0:
            warnings.append("Odd number of samples for interleaved I/Q; trailing sample dropped.")
        total_samples = total_scalars // 2
        scalar_offset = sample_offset * 2
        count = -1 if max_samples is None else max_samples * 2
    elif fmt.layout == "separate_iq":
        half = total_scalars // 2
        total_samples = half
        scalar_offset = min(sample_offset, half)
        available = max(0, half - scalar_offset)
        count = available if max_samples is None else min(max_samples, available)
    elif fmt.layout == "real_only":
        total_samples = total_scalars
        scalar_offset = min(sample_offset, total_scalars)
        available = max(0, total_scalars - scalar_offset)
        count = available if max_samples is None else min(max_samples, available)
    else:
        raise ValueError(f"Unknown layout: {fmt.layout}")

    if fmt.layout == "separate_iq":
        half = total_scalars // 2
        offset_bytes = scalar_offset * np.dtype(DTYPE_MAP[fmt.dtype]).itemsize
        i = _read_typed(path, fmt.dtype, fmt.endian, count=count, offset=offset_bytes)
        q = _read_typed(
            path,
            fmt.dtype,
            fmt.endian,
            count=count,
            offset=offset_bytes + half * np.dtype(DTYPE_MAP[fmt.dtype]).itemsize,
        )
        is_complex = True
    elif fmt.layout == "real_only":
        i = _read_typed(
            path,
            fmt.dtype,
            fmt.endian,
            count=count,
            offset=scalar_offset * np.dtype(DTYPE_MAP[fmt.dtype]).itemsize,
        )
        q = np.zeros_like(i)
        is_complex = False
    else:
        offset_bytes = scalar_offset * np.dtype(DTYPE_MAP[fmt.dtype]).itemsize
        raw = _read_typed(path, fmt.dtype, fmt.endian, count=count, offset=offset_bytes)
        if len(raw) % 2 != 0:
            raw = raw[:-1]
        i = raw[0::2]
        q = raw[1::2]
        is_complex = True

    if fmt.dtype in ("uint8", "uint16") and fmt.signed_offset:
        midpoint = float(np.iinfo(DTYPE_MAP[fmt.dtype]).max + 1) / 2.0
        i = (i.astype(np.float64) - midpoint) / midpoint
        q = (q.astype(np.float64) - midpoint) / midpoint
    else:
        if not np.issubdtype(DTYPE_MAP[fmt.dtype], np.floating):
            info = np.iinfo(DTYPE_MAP[fmt.dtype])
            scale = max(abs(info.min), info.max)
            i = i.astype(np.float64) / scale
            q = q.astype(np.float64) / scale
        else:
            i = i.astype(np.float64)
            q = q.astype(np.float64)

    complex_samples = (i + 1j * q).astype(np.complex64)

    if fmt.sample_rate_hz:
        sr_est = Estimate(
            name="sample_rate",
            value=float(fmt.sample_rate_hz),
            unit="Hz",
            source=Source.USER_SUPPLIED,
            evidence=["Value entered by the user in the raw-IQ import dialog."],
        )
    else:
        sr_est = Estimate(
            name="sample_rate",
            value=None,
            unit="Hz",
            source=Source.UNKNOWN,
            warnings=[
                "No sample rate provided and none is recoverable from a raw IQ "
                "file. Time/frequency axes cannot be labeled until one is supplied."
            ],
        )

    cf_est = None
    if fmt.center_frequency_hz is not None:
        cf_est = Estimate(
            name="center_frequency",
            value=float(fmt.center_frequency_hz),
            unit="Hz",
            source=Source.USER_SUPPLIED,
        )

    metadata = RecordingMetadata(
        sample_rate=sr_est,
        center_frequency=cf_est,
        is_complex=is_complex,
        channel_count=1,
        sample_dtype=fmt.dtype,
        duration_seconds=(total_samples / fmt.sample_rate_hz) if fmt.sample_rate_hz else None,
        total_samples=total_samples,
        extra={
            "layout": fmt.layout,
            "endian": fmt.endian,
            "warnings": warnings,
            "loaded_samples": len(complex_samples),
        },
    )
    return Recording(samples=complex_samples, metadata=metadata, source_path=str(path))
