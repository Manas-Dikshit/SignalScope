from __future__ import annotations

import io
import uuid
import wave

import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import SignalFingerprint


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


async def _create_project(
    client: AsyncClient, headers: dict, name: str = "Gallery Project"
) -> tuple[str, str]:
    np.random.seed(21 + sum(name.encode()) % 997)
    samples = (np.random.randn(2048) + 1j * np.random.randn(2048)).astype(np.complex64) * 0.1
    upload = await client.post(
        "/api/recordings/upload",
        headers=headers,
        files={"file": (f"{name}.wav", _make_wav_bytes(samples), "audio/wav")},
        data={"loader": "wav"},
    )
    assert upload.status_code in (200, 201), upload.text
    recording_id = upload.json()["id"]

    create = await client.post(
        "/api/projects",
        headers=headers,
        json={"name": name, "recording_id": recording_id},
    )
    assert create.status_code == 201, create.text
    return create.json()["id"], recording_id


def _add_fingerprint(
    db: AsyncSession,
    project_id: str,
    recording_id: str,
    vector: list[float],
) -> None:
    db.add(
        SignalFingerprint(
            project_id=uuid.UUID(project_id),
            recording_id=uuid.UUID(recording_id),
            version="1",
            dimensions=len(vector),
            vector_json=vector,
            embedding_json=vector,
            features_json={"spectral_flatness": 0.2},
        )
    )


async def _register_user(client: AsyncClient, email: str) -> dict:
    await client.post(
        "/api/auth/register", json={"email": email, "password": "gallery-pass-123"}
    )
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": "gallery-pass-123"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_similar_requires_fingerprint(client: AsyncClient, auth_headers: dict):
    project_id, _ = await _create_project(client, auth_headers)

    resp = await client.get(f"/api/projects/{project_id}/similar", headers=auth_headers)
    assert resp.status_code == 404
    assert "Run parameter estimation" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_similar_returns_ranked_neighbours(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    project_a, rec_a = await _create_project(client, auth_headers, "Gallery A")
    project_b, rec_b = await _create_project(client, auth_headers, "Gallery B")
    project_c, rec_c = await _create_project(client, auth_headers, "Gallery C")

    _add_fingerprint(db_session, project_a, rec_a, [1.0, 0.0, 0.0])
    _add_fingerprint(db_session, project_b, rec_b, [0.99, 0.05, 0.0])
    _add_fingerprint(db_session, project_c, rec_c, [0.0, 1.0, 0.0])
    await db_session.commit()

    resp = await client.get(f"/api/projects/{project_a}/similar", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert [n["project_id"] for n in data["neighbors"]] == [project_b, project_c]
    assert data["neighbors"][0]["distance"] < data["neighbors"][1]["distance"]
    assert data["nearest_distance"] == data["neighbors"][0]["distance"]
    assert data["rare_signal"] is False
    assert data["fingerprint"]["version"] == "1"
    assert "not an identification" in data["method"]


@pytest.mark.asyncio
async def test_distant_only_gallery_flags_rare_candidate(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    project_a, rec_a = await _create_project(client, auth_headers, "Rare A")
    project_b, rec_b = await _create_project(client, auth_headers, "Rare B")

    _add_fingerprint(db_session, project_a, rec_a, [1.0, 0.0, 0.0])
    _add_fingerprint(db_session, project_b, rec_b, [0.0, 1.0, 0.0])
    await db_session.commit()

    resp = await client.get(f"/api/projects/{project_a}/similar", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["nearest_distance"] > data["threshold"]
    assert data["rare_signal"] is True


@pytest.mark.asyncio
async def test_empty_gallery_does_not_claim_rarity(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    project_a, rec_a = await _create_project(client, auth_headers, "Lone A")
    _add_fingerprint(db_session, project_a, rec_a, [1.0, 0.0, 0.0])
    await db_session.commit()

    resp = await client.get(f"/api/projects/{project_a}/similar", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["neighbors"] == []
    assert data["nearest_distance"] is None
    assert data["rare_signal"] is None


@pytest.mark.asyncio
async def test_gallery_is_scoped_to_project_owner(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    project_a, rec_a = await _create_project(client, auth_headers, "Owner A")
    _add_fingerprint(db_session, project_a, rec_a, [1.0, 0.0, 0.0])

    intruder = await _register_user(client, "gallery_intruder@example.com")
    project_b, rec_b = await _create_project(client, intruder, "Intruder B")
    _add_fingerprint(db_session, project_b, rec_b, [1.0, 0.0, 0.0])
    await db_session.commit()

    resp = await client.get(f"/api/projects/{project_a}/similar", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["neighbors"] == []

    forbidden = await client.get(f"/api/projects/{project_a}/similar", headers=intruder)
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_internal_similar_tool_returns_neighbours(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")
    project_a, rec_a = await _create_project(client, auth_headers, "Tool A")
    project_b, rec_b = await _create_project(client, auth_headers, "Tool B")
    _add_fingerprint(db_session, project_a, rec_a, [1.0, 0.0, 0.0])
    _add_fingerprint(db_session, project_b, rec_b, [0.98, 0.02, 0.0])
    await db_session.commit()

    resp = await client.post(
        "/internal/dsp-tools/search_similar_recordings",
        headers={"X-Internal-Token": "secret"},
        json={"project_id": project_a, "args": {"limit": 3}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["neighbors"][0]["project_id"] == project_b
    assert data["rare_signal"] is False


@pytest.mark.asyncio
async def test_internal_similar_tool_handles_missing_fingerprint(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret")
    project_id, _ = await _create_project(client, auth_headers, "Tool Missing")

    resp = await client.post(
        "/internal/dsp-tools/search_similar_recordings",
        headers={"X-Internal-Token": "secret"},
        json={"project_id": project_id, "args": {}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["neighbors"] == []
    assert data["rare_signal"] is None
    assert data["warnings"]
