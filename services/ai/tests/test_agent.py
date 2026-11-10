from __future__ import annotations

import pytest

from app.agent import run_analyst
from app.backend import FakeBackend
from app.schemas import InsightRequest
from app.validation import render_template, validate_insight

EVIDENCE = {
    "estimates": [
        {"name": "modulation", "value": "QPSK", "unit": None, "confidence": 0.64},
        {"name": "symbol_rate", "value": 125000.0, "unit": "symbols/s", "confidence": 0.72},
        {"name": "snr_db", "value": 12.3, "unit": "dB", "confidence": 0.8},
    ]
}


def test_fake_backend_returns_valid_cited_brief():
    request = InsightRequest(project_id="p1", evidence=EVIDENCE)
    result = run_analyst(request)
    assert result.summary
    assert "QPSK" in result.summary
    assert "125,000" in result.summary
    assert "modulation" in result.citations
    assert result.model_name == "fake-backend"


def test_render_template_marks_unknown_values():
    assert render_template("{{estimate:missing}}", EVIDENCE) == "[unknown:missing]"


def test_validation_rejects_unknown_citation():
    raw = FakeBackend().generate(InsightRequest(project_id="p1", evidence=EVIDENCE))
    raw["citations"]["not_real"] = "bad"
    with pytest.raises(ValueError):
        validate_insight(raw, EVIDENCE)


def test_validation_rejects_unknown_placeholder():
    raw = FakeBackend().generate(InsightRequest(project_id="p1", evidence=EVIDENCE))
    raw["summary_template"] = "bad {{estimate:not_real}}"
    with pytest.raises(ValueError):
        validate_insight(raw, EVIDENCE)
