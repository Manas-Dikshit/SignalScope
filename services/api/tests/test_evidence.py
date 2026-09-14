"""Evidence/proof layer end-to-end: deep-analysis returns plot-ready proof
spectra, ranked de-interleaving candidates (incl. diagonal + pseudo-random), a
FEC-type dispatch, and the Celery estimate job persists proofs + burst
alternatives in evidence_json."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.test_projects import _upload_recording


async def _make_project(client: AsyncClient, headers: dict, name: str) -> str:
    rec_id = await _upload_recording(client, headers)
    resp = await client.post("/api/projects", headers=headers, json={
        "name": name, "recording_id": rec_id,
    })
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_deep_analysis_returns_proof_spectra(client: AsyncClient, auth_headers: dict):
    project_id = await _make_project(client, auth_headers, "Evidence")
    resp = await client.get(f"/api/projects/{project_id}/analysis", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    proof = data["modulation"]["proof"]
    for order_name in ("order_2", "order_4", "order_8"):
        assert order_name in proof
        spec = proof[order_name]
        assert len(spec["freqs"]) == len(spec["power"]) > 0
        assert 0.0 <= spec["peakiness"] <= 1.0
    assert isinstance(data["modulation"]["warnings"], list)

    cands = data["symbol_rate_candidates"]
    assert len(cands) >= 1
    assert abs(data["symbol_rate_hz"] - cands[0]["value"]) < 1e-9

    algos = {c["algorithm"] for c in data["deinterleave"]["candidates"]}
    assert {"none", "block", "convolutional", "diagonal", "pseudo_random"} == algos
    for c in data["deinterleave"]["candidates"]:
        assert "run_length_histogram" in c
        assert {"run_lengths", "counts", "max_run"} <= set(c["run_length_histogram"])
    assert data["fec"]["fec_type"] == "convolutional"
    assert "path_metric" in data["fec"] or data["fec"]["path_metric"] is None


@pytest.mark.asyncio
async def test_deep_analysis_fec_type_dispatch(client: AsyncClient, auth_headers: dict):
    project_id = await _make_project(client, auth_headers, "FEC Dispatch")
    for fec_type in ("reed_solomon", "ldpc", "concatenated", "convolutional"):
        resp = await client.get(
            f"/api/projects/{project_id}/analysis?fec_type={fec_type}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fec"]["fec_type"] == fec_type
        assert data["fec"]["decoded_bits_count"] >= 0
        assert data["fec"]["stage_failed"] is None or isinstance(data["fec"]["stage_failed"], str)
        if fec_type == "reed_solomon":
            assert data["fec"]["corrected_symbols"] >= 0
            assert data["fec"]["corrected_erasures"] >= 0


@pytest.mark.asyncio
async def test_estimate_task_persists_proofs_and_burst_alternatives(
    client: AsyncClient, auth_headers: dict,
):
    project_id = await _make_project(client, auth_headers, "Persisted Evidence")
    resp = await client.post(f"/api/projects/{project_id}/estimate-parameters", headers=auth_headers)
    assert resp.status_code == 202

    resp = await client.get(f"/api/projects/{project_id}/parameters", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    by_name = {}
    for row in rows:
        by_name.setdefault(row["parameter_name"], []).append(row)

    mod_rows = by_name.get("modulation", [])
    assert mod_rows, "modulation estimate row must exist"
    row = mod_rows[0]
    assert "proof" in row["evidence_json"]
    for order_name in ("order_2", "order_4", "order_8"):
        assert order_name in row["evidence_json"]["proof"]

    burst_rows = [r for r in rows if r["parameter_name"].startswith("burst_")]
    assert burst_rows, "burst stats rows must exist"
    for r in burst_rows:
        assert "alternatives" in r["evidence_json"]