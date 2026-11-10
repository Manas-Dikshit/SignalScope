from __future__ import annotations

import io
import wave

import numpy as np
import pytest
from httpx import AsyncClient

from app.config import settings


def _make_wav_bytes(samples: np.ndarray, sample_rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        interleaved = np.empty(len(samples) * 2, dtype=np.int16)
        interleaved[0::2] = (samples.real * 32767).astype(np.int16)
        interleaved[1::2] = (samples.imag * 32767).astype(np.int16)
        wf.writeframes(interleaved.tobytes())
    return buf.getvalue()


async def _create_project(client: AsyncClient, headers: dict) -> str:
    np.random.seed(7)
    samples = (np.random.randn(4096) + 1j * np.random.randn(4096)).astype(np.complex64) * 0.1
    upload = await client.post(
        "/api/recordings/upload",
        headers=headers,
        files={"file": ("insight_test.wav", _make_wav_bytes(samples), "audio/wav")},
        data={"loader": "wav"},
    )
    assert upload.status_code in (200, 201), upload.text

    create = await client.post(
        "/api/projects",
        headers=headers,
        json={"name": "Insight Project", "recording_id": upload.json()["id"]},
    )
    assert create.status_code == 201, create.text
    return create.json()["id"]


def _fake_response(project_id: str) -> dict:
    return {
        "summary_template": "DSP supports {{estimate:modulation}}.",
        "summary": "",
        "hypothesis": {
            "label": "QPSK",
            "agreement_with_dsp": True,
            "confidence_note": "cited",
            "evidence_refs": ["modulation"],
        },
        "conflicts": [],
        "anomalies": [],
        "recommended_actions": [],
        "unknowns": [],
        "limitations": ["AI-generated hypothesis."],
        "citations": {"modulation": "parameter_estimates.modulation"},
        "tool_trace": [],
        "model_name": "fake-backend",
        "prompt_version": "test",
    }


@pytest.mark.asyncio
async def test_insights_disabled_returns_503(client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    project_id = await _create_project(client, auth_headers)

    resp = await client.post(f"/api/projects/{project_id}/insights", headers=auth_headers)
    assert resp.status_code == 503
    assert "AI insights are disabled" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_insights_latest_404_before_generation(client: AsyncClient, auth_headers: dict):
    project_id = await _create_project(client, auth_headers)

    resp = await client.get(f"/api/projects/{project_id}/insights", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_insights_reject_other_users_project(client: AsyncClient, auth_headers: dict):
    project_id = await _create_project(client, auth_headers)

    await client.post(
        "/api/auth/register",
        json={"email": "insight_intruder@example.com", "password": "intruder-pass"},
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": "insight_intruder@example.com", "password": "intruder-pass"},
    )
    intruder_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/api/projects/{project_id}/insights", headers=intruder_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_insights_generate_and_store(client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    project_id = await _create_project(client, auth_headers)

    calls: list[str] = []

    def fake_request(pid: str, evidence: dict, images=None) -> dict:
        calls.append(pid)
        return _fake_response(pid)

    monkeypatch.setattr("app.ai_client.request_insight_sync", fake_request)

    resp = await client.post(f"/api/projects/{project_id}/insights", headers=auth_headers)
    assert resp.status_code == 202
    assert calls == [project_id]

    latest = await client.get(f"/api/projects/{project_id}/insights", headers=auth_headers)
    assert latest.status_code == 200
    data = latest.json()
    assert data["status"] == "completed"
    assert data["model_name"] == "fake-backend"
    assert data["citations_json"] == {"modulation": "parameter_estimates.modulation"}


@pytest.mark.asyncio
async def test_insights_failure_keeps_dsp_results(client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    project_id = await _create_project(client, auth_headers)

    def broken_request(*args, **kwargs) -> dict:
        raise RuntimeError("sidecar offline")

    monkeypatch.setattr("app.ai_client.request_insight_sync", broken_request)

    resp = await client.post(f"/api/projects/{project_id}/insights", headers=auth_headers)
    assert resp.status_code == 202

    latest = await client.get(f"/api/projects/{project_id}/insights", headers=auth_headers)
    assert latest.status_code == 200
    data = latest.json()
    assert data["status"] == "failed"
    assert "sidecar offline" in data["error_message"]

    # DSP results are untouched by an AI failure.
    project = await client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert project.status_code == 200
