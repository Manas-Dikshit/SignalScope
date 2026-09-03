import json

import numpy as np

from signalscope_dsp.io import load_sigmf
from signalscope_dsp.common import Source


def test_load_sigmf(tmp_path):
    n = 500
    i = np.linspace(-1, 1, n).astype(np.float32)
    q = np.linspace(1, -1, n).astype(np.float32)
    interleaved = np.empty(2 * n, dtype=np.float32)
    interleaved[0::2] = i
    interleaved[1::2] = q
    data_path = tmp_path / "rec.sigmf-data"
    interleaved.tofile(data_path)

    meta = {
        "global": {"core:datatype": "cf32_le", "core:sample_rate": 1_000_000},
        "captures": [{"core:frequency": 915_000_000, "core:sample_start": 0}],
        "annotations": [],
    }
    meta_path = tmp_path / "rec.sigmf-meta"
    with open(meta_path, "w") as f:
        json.dump(meta, f)

    rec = load_sigmf(meta_path)
    assert rec.metadata.sample_rate.source == Source.METADATA
    assert rec.metadata.sample_rate.value == 1_000_000
    assert rec.metadata.center_frequency.value == 915_000_000
    assert len(rec.samples) == n
