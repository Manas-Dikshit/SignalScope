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


def _read_typed(path: Path, dtype: str, endian: str) -> np.ndarray:
    base = np.dtype(DTYPE_MAP[dtype])
    byteorder = "<" if endian == "little" else ">"
    typed = base.newbyteorder(byteorder) if base.itemsize > 1 else base
    return np.fromfile(path, dtype=typed)


def load_raw_iq(path: str | Path, fmt: RawIQFormat) -> Recording:
    path = Path(path)
    raw = _read_typed(path, fmt.dtype, fmt.endian)

    if fmt.dtype in ("uint8", "uint16") and fmt.signed_offset:
        midpoint = float(np.iinfo(DTYPE_MAP[fmt.dtype]).max + 1) / 2.0
        raw = raw.astype(np.float64) - midpoint
    else:
        raw = raw.astype(np.float64)

    if not np.issubdtype(DTYPE_MAP[fmt.dtype], np.floating):
        info = np.iinfo(DTYPE_MAP[fmt.dtype])
        scale = max(abs(info.min), info.max)
        raw = raw / scale

    warnings: list[str] = []

    if fmt.layout == "interleaved":
        if len(raw) % 2 != 0:
            raw = raw[:-1]
            warnings.append("Odd number of samples for interleaved I/Q; trailing sample dropped.")
        i = raw[0::2]
        q = raw[1::2]
        is_complex = True
    elif fmt.layout == "separate_iq":
        half = len(raw) // 2
        i = raw[:half]
        q = raw[half:half * 2]
        is_complex = True
    elif fmt.layout == "real_only":
        i = raw
        q = np.zeros_like(raw)
        is_complex = False
    else:
        raise ValueError(f"Unknown layout: {fmt.layout}")

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
        duration_seconds=(len(complex_samples) / fmt.sample_rate_hz) if fmt.sample_rate_hz else None,
        total_samples=len(complex_samples),
        extra={"layout": fmt.layout, "endian": fmt.endian, "warnings": warnings},
    )
    return Recording(samples=complex_samples, metadata=metadata, source_path=str(path))
