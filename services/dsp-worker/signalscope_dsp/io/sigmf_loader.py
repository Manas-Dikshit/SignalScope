from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..common import Estimate, Recording, RecordingMetadata, Source

# SigMF dataset-format string -> numpy dtype, is_complex
SIGMF_DTYPES = {
    "cf32_le": (np.complex64, True),
    "cf64_le": (np.complex128, True),
    "ci16_le": ("i2i2", True),
    "ci8": ("i1i1", True),
    "rf32_le": (np.float32, False),
    "rf64_le": (np.float64, False),
    "ri16_le": (np.int16, False),
    "ri8": (np.int8, False),
}


def load_sigmf(meta_path: str | Path) -> Recording:
    """Load a .sigmf-meta + .sigmf-data pair.

    SigMF is the preferred format because it is self-describing: sample rate and
    center frequency, if present, are trusted as exact metadata rather than
    estimated.
    """
    meta_path = Path(meta_path)
    with open(meta_path) as f:
        meta = json.load(f)

    global_info = meta.get("global", {})
    captures = meta.get("captures", [{}])
    dtype_str = global_info.get("core:datatype", "cf32_le")

    data_path = meta_path.with_suffix("").with_suffix(".sigmf-data")
    if not data_path.exists():
        # try replacing suffix directly (some tools name it <base>.sigmf-data)
        data_path = meta_path.parent / (meta_path.stem.replace(".sigmf-meta", "") + ".sigmf-data")
    if not data_path.exists():
        raise FileNotFoundError(f"Could not locate SigMF data file next to {meta_path}")

    if dtype_str in ("ci16_le", "ci8"):
        sub_dtype = np.int16 if dtype_str == "ci16_le" else np.int8
        raw = np.fromfile(data_path, dtype=sub_dtype).astype(np.float64)
        max_val = np.iinfo(sub_dtype).max
        raw /= max_val
        i, q = raw[0::2], raw[1::2]
        samples = (i + 1j * q).astype(np.complex64)
        is_complex = True
    else:
        np_dtype, is_complex = SIGMF_DTYPES.get(dtype_str, (np.complex64, True))
        raw = np.fromfile(data_path, dtype=np_dtype)
        if is_complex:
            samples = raw.astype(np.complex64)
        else:
            samples = (raw.astype(np.float64) + 0j).astype(np.complex64)

    sample_rate = global_info.get("core:sample_rate")
    sr_est = Estimate(
        name="sample_rate",
        value=float(sample_rate) if sample_rate else None,
        unit="Hz",
        source=Source.METADATA if sample_rate else Source.UNKNOWN,
        evidence=["core:sample_rate from sigmf-meta"] if sample_rate else [],
        warnings=[] if sample_rate else ["sigmf-meta did not include core:sample_rate."],
    )

    center_freq = captures[0].get("core:frequency") if captures else None
    cf_est = None
    if center_freq is not None:
        cf_est = Estimate(
            name="center_frequency",
            value=float(center_freq),
            unit="Hz",
            source=Source.METADATA,
            evidence=["captures[0]['core:frequency'] from sigmf-meta"],
        )

    metadata = RecordingMetadata(
        sample_rate=sr_est,
        center_frequency=cf_est,
        is_complex=is_complex,
        channel_count=1,
        sample_dtype=dtype_str,
        duration_seconds=(len(samples) / sample_rate) if sample_rate else None,
        total_samples=len(samples),
        extra={"sigmf_global": global_info, "sigmf_captures": captures},
    )
    return Recording(samples=samples, metadata=metadata, source_path=str(data_path))
