from __future__ import annotations

import io
import uuid
import wave

import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ParameterEstimate


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
    np.random.seed(11)
    samples = (np.random.randn(8192) + 1j * np.random.randn(8192)).astype(np.complex64) * 0.1
    upload = await client.post(
        "/api/recordings/upload",
        headers=headers,
        files={"file": ("tool_test.wav", _make_wav_bytes(samples), "audio/wav")},
        data={"loader": "wav"},
    )
    assert upload.status_code in (200, 201), upload.text

    create = await client.post(
        "/api/projects",
        headers=headers,
        json={"name": "Tool Project", "recording_id": upload.json()["id"]},
    )
    assert create.status_code == 201, create.text
    return create.json()["id"]


@pytest.mark.asyncio
async def test_internal_tool_requires_valid_token(client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")
    project_id = await _create_project(client, auth_headers)

    missing = await client.post(
        "/internal/dsp-tools/get_project_evidence",
        json={"project_id": project_id, "args": {}},
    )
    assert missing.status_code == 403

    wrong = await client.post(
        "/internal/dsp-tools/get_project_evidence",
        headers={"X-Internal-Token": "wrong"},
        json={"project_id": project_id, "args": {}},
    )
    assert wrong.status_code == 403


@pytest.mark.asyncio
async def test_internal_tool_rejects_unknown_tool(client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")
    project_id = await _create_project(client, auth_headers)

    resp = await client.post(
        "/internal/dsp-tools/rm_rf",
        headers={"X-Internal-Token": "secret"},
        json={"project_id": project_id, "args": {}},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_project_evidence_returns_cited_estimates(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch,
):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")
    project_id = await _create_project(client, auth_headers)

    db_session.add(
        ParameterEstimate(
            project_id=uuid.UUID(project_id),
            parameter_name="modulation",
            value_json={"value": "QPSK", "unit": None},
            value_type="categorical",
            confidence=0.42,
            evidence_json={"evidence": ["mth-power peak at 2x"], "warnings": []},
            source="dsp",
        )
    )
    await db_session.commit()

    resp = await client.post(
        "/internal/dsp-tools/get_project_evidence",
        headers={"X-Internal-Token": "secret"},
        json={"project_id": project_id, "args": {}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["estimates"][0]["name"] == "modulation"
    assert data["estimates"][0]["confidence"] == 0.42


@pytest.mark.asyncio
async def test_run_deep_analysis_tool(client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")
    project_id = await _create_project(client, auth_headers)

    resp = await client.post(
        "/internal/dsp-tools/run_deep_analysis",
        headers={"X-Internal-Token": "secret"},
        json={"project_id": project_id, "args": {"fec_type": "convolutional"}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sample_rate_hz"] == 8000
    assert "modulation" in data
    assert "fec" in data
    assert "deinterleave" in data
    assert "n_bits" in data["demodulation"]


@pytest.mark.asyncio
async def test_try_demodulation_tool(client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")
    project_id = await _create_project(client, auth_headers)

    resp = await client.post(
        "/internal/dsp-tools/try_demodulation",
        headers={"X-Internal-Token": "secret"},
        json={
            "project_id": project_id,
            "args": {"modulation": "QPSK", "samples_per_symbol": 8},
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["modulation"] == "QPSK"
    assert data["bits_per_symbol"] == 2
    assert data["n_bits"] > 0
    assert data["samples_per_symbol"] == 8
    assert isinstance(data["first_bytes_hex"], str)


@pytest.mark.asyncio
async def test_try_fec_tool(client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")
    project_id = await _create_project(client, auth_headers)

    resp = await client.post(
        "/internal/dsp-tools/try_fec",
        headers={"X-Internal-Token": "secret"},
        json={"project_id": project_id, "args": {"fec_type": "reed_solomon"}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["fec_type"] == "reed_solomon"
    assert data["fec"]["fec_type"] == "reed_solomon"
    assert "crc_valid" in data["fec"] or "crc_detail" in data["fec"]


@pytest.mark.asyncio
async def test_tool_rejects_invalid_arguments(client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")
    project_id = await _create_project(client, auth_headers)

    resp = await client.post(
        "/internal/dsp-tools/try_demodulation",
        headers={"X-Internal-Token": "secret"},
        json={"project_id": project_id, "args": {"modulation": "NOT-A-MOD"}},
    )
    assert resp.status_code == 422
