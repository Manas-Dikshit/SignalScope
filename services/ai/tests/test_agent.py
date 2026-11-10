from __future__ import annotations

import httpx
import pytest

from app import agent as agent_module
from app.agent import MAX_STEPS, run_analyst
from app.backend import FakeBackend, deterministic_payload
from app.config import settings
from app.schemas import InsightRequest
from app.tools import dispatch_tool, parse_tool_call
from app.validation import render_template, validate_insight

EVIDENCE = {
    "estimates": [
        {"name": "modulation", "value": "QPSK", "unit": None, "confidence": 0.64},
        {"name": "symbol_rate", "value": 125000.0, "unit": "symbols/s", "confidence": 0.72},
        {"name": "snr_db", "value": 12.3, "unit": "dB", "confidence": 0.8},
    ]
}

LOW_CONFIDENCE_EVIDENCE = {
    "recording": {"sample_rate_hz": 48000},
    "estimates": [
        {
            "name": "modulation",
            "value": "8-PSK",
            "confidence": 0.41,
            "alternatives": [{"label": "QPSK", "confidence": 0.33}],
        },
        {"name": "symbol_rate", "value": 2400.0, "unit": "Hz", "confidence": 0.5},
    ],
}


def _fake_dispatch(call: dict, project_id: str) -> dict:
    return {
        "tool": call.get("name"),
        "ok": True,
        "result": {"modulation": "QPSK", "n_bits": 128, "first_bytes_hex": "deadbeef"},
    }


def test_fake_backend_returns_valid_cited_brief():
    request = InsightRequest(project_id="p1", evidence=EVIDENCE)
    result = run_analyst(request)
    assert result.summary
    assert "QPSK" in result.summary
    assert "125,000" in result.summary
    assert "modulation" in result.citations
    assert result.model_name == "fake-backend"
    assert result.tool_trace == []


def test_low_confidence_modulation_triggers_follow_up_tool():
    request = InsightRequest(project_id="p1", evidence=LOW_CONFIDENCE_EVIDENCE)
    result = run_analyst(request, dispatch=_fake_dispatch)

    assert len(result.tool_trace) == 1
    entry = result.tool_trace[0]
    assert entry["tool"] == "try_demodulation"
    assert entry["arguments"]["modulation"] == "QPSK"
    assert entry["arguments"]["samples_per_symbol"] == 20  # 48000 / 2400
    assert entry["result"]["ok"] is True


def test_high_confidence_modulation_skips_tools():
    request = InsightRequest(project_id="p1", evidence=EVIDENCE)
    result = run_analyst(request, dispatch=_fake_dispatch)
    assert result.tool_trace == []


def test_tool_call_allowlist_rejects_unknown_tool():
    with pytest.raises(ValueError):
        parse_tool_call({"name": "rm_rf", "arguments": {}})


def test_tool_trace_validation_rejects_unknown_tool():
    payload = deterministic_payload(EVIDENCE)
    with pytest.raises(ValueError):
        validate_insight(payload, EVIDENCE, tool_trace=[{"tool": "rm_rf"}])


def test_dispatch_tool_posts_to_private_route_with_token(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")
    monkeypatch.setattr(settings, "API_INTERNAL_URL", "http://api:8000")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/dsp-tools/try_demodulation"
        assert request.headers["X-Internal-Token"] == "secret"
        return httpx.Response(200, json={"n_bits": 64, "modulation": "QPSK"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = dispatch_tool(
        {"name": "try_demodulation", "arguments": {"modulation": "QPSK"}},
        "project-1",
        client=client,
    )
    assert result["ok"] is True
    assert result["result"]["n_bits"] == 64


def test_dispatch_tool_reports_http_error_as_data(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="bad args")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = dispatch_tool(
        {"name": "run_deep_analysis", "arguments": {"fec_type": "convolutional"}},
        "project-1",
        client=client,
    )
    assert result["ok"] is False
    assert result["status"] == 422


def test_dispatch_tool_reports_timeout_as_data(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow tool")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = dispatch_tool({"name": "get_project_evidence", "arguments": {}}, "p", client=client)
    assert result["ok"] is False
    assert "timed out" in result["error"]


def test_loop_stops_at_max_steps(monkeypatch):
    class StubbornBackend:
        name = "stubborn"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools=None, *, request=None, response_format=None, **kwargs):
            self.calls += 1
            if tools:
                return {
                    "tool_calls": [
                        {"id": "x", "name": "get_project_evidence", "arguments": {}}
                    ]
                }
            return {"content": deterministic_payload(EVIDENCE)}

    backend = StubbornBackend()
    monkeypatch.setattr(agent_module, "get_backend", lambda: backend)

    result = run_analyst(InsightRequest(project_id="p1", evidence=EVIDENCE), dispatch=_fake_dispatch)

    assert backend.calls == MAX_STEPS + 1
    assert len(result.tool_trace) == MAX_STEPS
    assert result.summary


def test_invalid_model_output_falls_back_to_deterministic_brief(monkeypatch):
    class BadBackend:
        name = "bad"

        def chat(self, messages, tools=None, *, request=None, response_format=None, **kwargs):
            return {"content": {"summary_template": "invented 123 MHz", "citations": {}}}

    monkeypatch.setattr(agent_module, "get_backend", lambda: BadBackend())

    result = run_analyst(InsightRequest(project_id="p1", evidence=EVIDENCE))

    assert "DSP evidence currently supports" in result.summary
    assert any("Model output rejected" in item for item in result.limitations)


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


def test_no_evidence_produces_honest_brief():
    request = InsightRequest(project_id="p1", evidence={"estimates": []})
    result = run_analyst(request, dispatch=_fake_dispatch)
    assert "No DSP estimates" in result.summary
    assert result.tool_trace == []


FINGERPRINT_EVIDENCE = {
    **EVIDENCE,
    "fingerprint": {"version": "1", "dimensions": 22, "features": {}},
}


def _rare_dispatch(call: dict, project_id: str) -> dict:
    return {
        "tool": call.get("name"),
        "ok": True,
        "result": {
            "neighbors": [
                {
                    "project_id": "other",
                    "project_name": "Known QPSK",
                    "recording_filename": "known.wav",
                    "distance": 0.81,
                    "similarity": 0.19,
                }
            ],
            "nearest_distance": 0.81,
            "threshold": 0.35,
            "rare_signal": True,
        },
    }


def test_fingerprint_evidence_triggers_gallery_lookup():
    request = InsightRequest(project_id="p1", evidence=FINGERPRINT_EVIDENCE)
    result = run_analyst(request, dispatch=_rare_dispatch)

    assert len(result.tool_trace) == 1
    entry = result.tool_trace[0]
    assert entry["tool"] == "search_similar_recordings"
    assert entry["arguments"] == {"limit": 5}
    assert entry["result"]["ok"] is True


def test_gallery_lookup_explains_rarity_without_identifying():
    request = InsightRequest(project_id="p1", evidence=FINGERPRINT_EVIDENCE)
    result = run_analyst(request, dispatch=_rare_dispatch)

    assert any("rare-signal candidate" in a.description for a in result.anomalies)
    assert any("not an identification" in item for item in result.limitations)


def test_search_similar_recordings_is_allowlisted():
    name, args = parse_tool_call(
        {"name": "search_similar_recordings", "arguments": {"limit": 3}}
    )
    assert name == "search_similar_recordings"
    assert args == {"limit": 3}
