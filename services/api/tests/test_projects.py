from __future__ import annotations

import io
import wave

import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisProject, Recording, RecordingMetadata


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


async def _upload_recording(client: AsyncClient, headers: dict) -> str:
    np.random.seed(42)
    samples = (np.random.randn(8000) + 1j * np.random.randn(8000)).astype(np.complex64) * 0.1
    wav_bytes = _make_wav_bytes(samples)
    resp = await client.post(
        "/api/recordings/upload",
        headers=headers,
        files={"file": ("project_test.wav", wav_bytes, "audio/wav")},
        data={"loader": "wav"},
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, auth_headers: dict):
    rec_id = await _upload_recording(client, auth_headers)

    resp = await client.post("/api/projects", headers=auth_headers, json={
        "name": "Test Project",
        "description": "A test project",
        "recording_id": rec_id,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Project"
    assert data["recording_id"] == rec_id


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/projects", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient, auth_headers: dict):
    rec_id = await _upload_recording(client, auth_headers)

    create_resp = await client.post("/api/projects", headers=auth_headers, json={
        "name": "Get Project",
        "recording_id": rec_id,
    })
    project_id = create_resp.json()["id"]

    resp = await client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == project_id


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, auth_headers: dict):
    rec_id = await _upload_recording(client, auth_headers)

    create_resp = await client.post("/api/projects", headers=auth_headers, json={
        "name": "Old Name",
        "recording_id": rec_id,
    })
    project_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/projects/{project_id}", headers=auth_headers, json={
        "name": "New Name",
        "description": "Updated description",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient, auth_headers: dict):
    rec_id = await _upload_recording(client, auth_headers)

    create_resp = await client.post("/api/projects", headers=auth_headers, json={
        "name": "Delete Project",
        "recording_id": rec_id,
    })
    project_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_estimate_parameters(client: AsyncClient, auth_headers: dict):
    rec_id = await _upload_recording(client, auth_headers)

    create_resp = await client.post("/api/projects", headers=auth_headers, json={
        "name": "Estimate Params",
        "recording_id": rec_id,
    })
    project_id = create_resp.json()["id"]

    resp = await client.post(f"/api/projects/{project_id}/estimate-parameters", headers=auth_headers)
    assert resp.status_code == 202
    job_data = resp.json()
    assert "id" in job_data
    assert job_data["status"] == "queued"


@pytest.mark.asyncio
async def test_list_parameters_empty(client: AsyncClient, auth_headers: dict):
    rec_id = await _upload_recording(client, auth_headers)

    create_resp = await client.post("/api/projects", headers=auth_headers, json={
        "name": "Empty Params",
        "recording_id": rec_id,
    })
    project_id = create_resp.json()["id"]

    resp = await client.get(f"/api/projects/{project_id}/parameters", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_cross_user_project_access_denied(client: AsyncClient):
    # User A
    await client.post("/api/auth/register", json={"email": "proj_user_a@example.com", "password": "pass_a"})
    login_a = await client.post("/api/auth/login", json={"email": "proj_user_a@example.com", "password": "pass_a"})
    headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}

    rec_id = await _upload_recording(client, headers_a)

    create_resp = await client.post("/api/projects", headers=headers_a, json={
        "name": "User A Project",
        "recording_id": rec_id,
    })
    project_id = create_resp.json()["id"]

    # User B
    await client.post("/api/auth/register", json={"email": "proj_user_b@example.com", "password": "pass_b"})
    login_b = await client.post("/api/auth/login", json={"email": "proj_user_b@example.com", "password": "pass_b"})
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    resp = await client.get(f"/api/projects/{project_id}", headers=headers_b)
    assert resp.status_code == 403
