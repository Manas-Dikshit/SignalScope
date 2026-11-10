import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_demo_samples(client: AsyncClient):
    response = await client.get("/api/recordings/demos")
    assert response.status_code == 200
    demos = response.json()
    assert len(demos) >= 5
    ids = [d["id"] for d in demos]
    assert "qpsk_48k" in ids
    assert "2fsk_48k" in ids
    assert "16qam_48k" in ids


@pytest.mark.asyncio
async def test_load_demo_sample(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/recordings/load-demo",
        json={"sample_id": "qpsk_48k"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    recording = response.json()
    assert recording["original_filename"] == "demo_qpsk_48k.wav"
    assert recording["file_format"] == "wav"
    assert recording["total_samples"] > 0

    # Idempotent re-load returns existing recording
    response_dup = await client.post(
        "/api/recordings/load-demo",
        json={"sample_id": "qpsk_48k"},
        headers=auth_headers,
    )
    assert response_dup.status_code == 201
    assert response_dup.json()["id"] == recording["id"]
