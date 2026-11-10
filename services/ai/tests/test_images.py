from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent import run_analyst
from app.config import settings
from app.schemas import InsightRequest

PNG_1X1 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

EVIDENCE = {
    "estimates": [
        {"name": "modulation", "value": "QPSK", "unit": None, "confidence": 0.7},
        {"name": "symbol_rate", "value": 125000.0, "unit": "symbols/s", "confidence": 0.7},
    ]
}


def test_image_data_uri_is_accepted_and_acknowledged():
    request = InsightRequest(
        project_id="p1", evidence=EVIDENCE, images={"psd.png": PNG_1X1}
    )
    result = run_analyst(request)
    assert any(
        "Visual second opinion reviewed: psd.png" in item for item in result.limitations
    )
    assert "Visual evidence reviewed." in result.hypothesis.confidence_note


def test_non_image_uri_is_rejected():
    with pytest.raises(ValidationError):
        InsightRequest(
            project_id="p1",
            evidence=EVIDENCE,
            images={"raw.iq": "data:application/octet-stream;base64,AAAA"},
        )


def test_arbitrary_url_is_rejected():
    with pytest.raises(ValidationError):
        InsightRequest(
            project_id="p1", evidence=EVIDENCE, images={"psd.png": "http://example.test/a.png"}
        )


def test_oversized_image_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_IMAGE_BYTES", 10)
    with pytest.raises(ValidationError):
        InsightRequest(
            project_id="p1", evidence=EVIDENCE, images={"psd.png": PNG_1X1}
        )


def test_total_image_bundle_cap_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_IMAGE_BYTES", 10_000)
    monkeypatch.setattr(settings, "AI_MAX_TOTAL_IMAGE_BYTES", 1)
    with pytest.raises(ValidationError):
        InsightRequest(
            project_id="p1", evidence=EVIDENCE, images={"psd.png": PNG_1X1}
        )
