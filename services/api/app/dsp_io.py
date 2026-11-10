from __future__ import annotations

"""Shared loader for interactive/analyst DSP windows.

Both the public deep-analysis route and the private tool endpoint cap their
reads. Keeping the loader logic here avoids a third copy of the format/params
mapping and keeps every caller's window bounded.
"""

from typing import Any

import numpy as np


def load_project_samples(
    project: Any,
    rec: Any,
    meta: Any,
    *,
    max_samples: int = 200_000,
) -> tuple[np.ndarray, float]:
    from signalscope_dsp.io import RawIQFormat, load_raw_iq, load_sigmf, load_wav

    loader = rec.file_format
    params: dict[str, Any] = {}
    if meta and meta.raw_metadata_json:
        if loader == "raw_iq":
            params = {
                "dtype": meta.data_type or "int16",
                "layout": meta.iq_layout or "interleaved",
                "endian": meta.endian or "little",
                "sample_rate_hz": meta.sample_rate,
                "center_frequency_hz": meta.center_frequency,
            }
        elif loader == "wav":
            params = {
                "stereo_mode": meta.raw_metadata_json.get(
                    "stereo_mode", "left_is_i_right_is_q"
                )
            }

    start = project.selected_start_sample or 0
    if loader == "wav":
        loaded = load_wav(
            rec.storage_path, sample_offset=start, max_samples=max_samples, **params
        )
    elif loader == "raw_iq":
        loaded = load_raw_iq(
            rec.storage_path,
            RawIQFormat(**params),
            sample_offset=start,
            max_samples=max_samples,
        )
    elif loader == "sigmf":
        loaded = load_sigmf(rec.storage_path, sample_offset=start, max_samples=max_samples)
    else:
        raise ValueError(f"Unknown format: {loader}")

    samples = loaded.samples
    if project.selected_end_sample is not None:
        samples = samples[: max(0, project.selected_end_sample - start)]

    sample_rate = loaded.metadata.sample_rate.value
    if not sample_rate and meta:
        sample_rate = meta.sample_rate
    if not sample_rate:
        raise ValueError("Sample rate unknown; cannot run DSP tools")

    return samples, float(sample_rate)
