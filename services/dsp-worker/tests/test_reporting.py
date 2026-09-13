import json

import numpy as np

from signalscope_dsp.common import Estimate, Source
from signalscope_dsp.reporting import AnalysisReport, build_report


def test_build_report_json_round_trip():
    estimates = [
        Estimate(name="sample_rate", value=2_000_000.0, unit="Hz",
                 source=Source.METADATA, evidence=["header"]),
        Estimate(name="modulation", value="QPSK", source=Source.HYPOTHESIS,
                 confidence=0.82, evidence=["4th-power peakiness"]),
    ]
    report = build_report(
        "smoke", "test.iq", estimates=estimates,
        artifacts={"snr_db": np.float64(20.5), "burst_count": np.int64(3)},
        warnings=["synthetic test"],
    )
    assert isinstance(report, AnalysisReport)
    payload = json.loads(report.to_json())
    assert payload["title"] == "smoke"
    assert payload["estimates"][0]["source"] == "metadata"
    assert payload["estimates"][1]["confidence"] == 0.82
    assert payload["artifacts"] == {"snr_db": 20.5, "burst_count": 3}
    assert payload["warnings"] == ["synthetic test"]
