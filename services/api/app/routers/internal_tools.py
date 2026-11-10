from __future__ import annotations

"""Private DSP tool endpoint used by the local Gemma 4 sidecar.

The AI service runs in its own container and never touches the database or the
recording volume. This route is the only bridge. It is gated by a shared secret
(``INTERNAL_API_TOKEN``) and every handler is a fixed allowlisted function, so a
model can never cause arbitrary code execution.
"""

import hmac
import logging
import uuid
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..dsp_io import load_project_samples
from ..models import AnalysisProject, ParameterEstimate, Recording, RecordingMetadata, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/dsp-tools", tags=["internal"])

FecType = Literal["convolutional", "reed_solomon", "ldpc", "concatenated"]
ModulationLabel = Literal["BPSK", "QPSK", "8-PSK", "16-QAM", "64-QAM", "2-FSK", "4-FSK"]


class InternalToolRequest(BaseModel):
    project_id: uuid.UUID
    args: dict[str, Any] = Field(default_factory=dict)


class DeepAnalysisArgs(BaseModel):
    fec_type: FecType = "convolutional"


class TryDemodulationArgs(BaseModel):
    modulation: ModulationLabel
    samples_per_symbol: int | None = Field(default=None, ge=2, le=64)


class TryFecArgs(BaseModel):
    fec_type: FecType = "convolutional"


class SearchSimilarRecordingsArgs(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)


def _require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    expected = settings.INTERNAL_API_TOKEN
    if not expected:
        raise HTTPException(status_code=403, detail="Internal tool route is disabled")
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=403, detail="Invalid internal token")


async def _project_bundle(
    project_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[AnalysisProject, Recording, RecordingMetadata | None]:
    result = await db.execute(
        select(AnalysisProject).where(
            AnalysisProject.id == project_id,
            AnalysisProject.status != "deleted",
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    rec = await db.get(Recording, project.recording_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    meta_result = await db.execute(
        select(RecordingMetadata).where(RecordingMetadata.recording_id == rec.id)
    )
    return project, rec, meta_result.scalar_one_or_none()


def _estimate_list(rows: list[ParameterEstimate]) -> list[dict[str, Any]]:
    estimates: list[dict[str, Any]] = []
    for row in rows:
        value = dict(row.value_json or {})
        value["name"] = row.parameter_name
        value["source"] = row.source
        value["confidence"] = row.confidence
        evidence_json = row.evidence_json or {}
        value.setdefault("evidence", evidence_json.get("evidence", []))
        value.setdefault("alternatives", evidence_json.get("alternatives", []))
        value.setdefault("warnings", evidence_json.get("warnings", []))
        estimates.append(value)
    return estimates


async def _get_project_evidence(
    project: AnalysisProject,
    rec: Recording,
    meta: RecordingMetadata | None,
    db: AsyncSession,
    _args: dict[str, Any],
) -> dict[str, Any]:
    result = await db.execute(
        select(ParameterEstimate)
        .where(ParameterEstimate.project_id == project.id)
        .order_by(ParameterEstimate.created_at)
    )
    return {
        "project_id": str(project.id),
        "project": {
            "name": project.name,
            "description": project.description,
            "selected_start_sample": project.selected_start_sample,
            "selected_end_sample": project.selected_end_sample,
        },
        "recording": {
            "filename": rec.original_filename,
            "format": rec.file_format,
            "sample_rate_hz": meta.sample_rate if meta else None,
            "center_frequency_hz": meta.center_frequency if meta else None,
            "duration_seconds": rec.duration_seconds,
            "total_samples": rec.total_samples,
        },
        "estimates": _estimate_list(result.scalars().all()),
    }


async def _run_deep_analysis(
    project: AnalysisProject,
    rec: Recording,
    meta: RecordingMetadata | None,
    db: AsyncSession,
    args: dict[str, Any],
) -> dict[str, Any]:
    from .projects import deep_analysis as deep_analysis_route

    parsed = DeepAnalysisArgs.model_validate(args)
    owner = await db.get(User, project.created_by)
    if not owner:
        raise HTTPException(status_code=404, detail="Project owner not found")

    response = await deep_analysis_route(
        project.id,
        fec_type=parsed.fec_type,
        user=owner,
        db=db,
    )
    data = response.model_dump()
    demod = data.get("demodulation") or {}
    return {
        "sample_rate_hz": data.get("sample_rate"),
        "window_start_sample": data.get("window_start_sample"),
        "window_end_sample": data.get("window_end_sample"),
        "modulation": data.get("modulation"),
        "symbol_rate_hz": data.get("symbol_rate_hz"),
        "symbol_rate_confidence": data.get("symbol_rate_confidence"),
        "symbol_rate_candidates": data.get("symbol_rate_candidates"),
        "features": data.get("features"),
        "demodulation": {
            "modulation": demod.get("modulation"),
            "samples_per_symbol": demod.get("samples_per_symbol"),
            "bits_per_symbol": demod.get("bits_per_symbol"),
            "n_symbols": demod.get("n_symbols"),
            "n_bits": demod.get("n_bits"),
            "first_bytes_hex": demod.get("first_bytes_hex"),
            "warnings": demod.get("warnings"),
        },
        "deinterleave": data.get("deinterleave"),
        "fec": data.get("fec"),
        "correlation": data.get("correlation"),
    }


async def _try_fec(
    project: AnalysisProject,
    rec: Recording,
    meta: RecordingMetadata | None,
    db: AsyncSession,
    args: dict[str, Any],
) -> dict[str, Any]:
    parsed = TryFecArgs.model_validate(args)
    data = await _run_deep_analysis(
        project, rec, meta, db, {"fec_type": parsed.fec_type}
    )
    return {
        "fec_type": parsed.fec_type,
        "deinterleave": data.get("deinterleave"),
        "fec": data.get("fec"),
        "correlation": data.get("correlation"),
    }


def _samples_per_symbol(samples: np.ndarray, sample_rate: float) -> int:
    from signalscope_dsp.modulation import estimate_symbol_rate_candidates

    candidates = estimate_symbol_rate_candidates(samples, sample_rate)
    rate = next((c.value for c in candidates if c.value), None)
    if not rate:
        return 8
    return max(2, min(64, int(round(sample_rate / float(rate)))))


async def _try_demodulation(
    project: AnalysisProject,
    rec: Recording,
    meta: RecordingMetadata | None,
    db: AsyncSession,
    args: dict[str, Any],
) -> dict[str, Any]:
    from signalscope_dsp.demodulation import demod_fsk, demod_psk, demod_qam
    from signalscope_dsp.fec.validation import bits_to_bytes
    from signalscope_dsp.preprocessing import ConditioningConfig, condition_signal

    parsed = TryDemodulationArgs.model_validate(args)
    samples, sample_rate = load_project_samples(project, rec, meta)
    conditioned = condition_signal(
        samples, sample_rate, ConditioningConfig(remove_dc_offset=True, normalize=True)
    )
    work = conditioned.samples

    sps = parsed.samples_per_symbol or _samples_per_symbol(work, sample_rate)
    modulation = parsed.modulation
    mode_order = {
        "BPSK": ("psk", 2),
        "QPSK": ("psk", 4),
        "8-PSK": ("psk", 8),
        "16-QAM": ("qam", 16),
        "64-QAM": ("qam", 64),
        "2-FSK": ("fsk", 2),
        "4-FSK": ("fsk", 4),
    }
    mode, order = mode_order[modulation]

    if mode == "qam":
        result = demod_qam(work, order, sps)
    elif mode == "fsk":
        result = demod_fsk(work, sample_rate, order, sps)
    else:
        result = demod_psk(work, order, sps)

    soft = result.soft_bits
    mean_margin = float(np.mean(np.abs(soft))) if soft is not None and len(soft) else None
    return {
        "modulation": modulation,
        "samples_per_symbol": sps,
        "bits_per_symbol": result.bits_per_symbol,
        "n_symbols": int(len(result.symbols)),
        "n_bits": int(len(result.hard_bits)),
        "first_bytes_hex": bits_to_bytes(result.hard_bits)[:32].hex(),
        "mean_soft_margin": mean_margin,
        "warnings": list(result.warnings),
    }


async def _search_similar_recordings(
    project: AnalysisProject,
    rec: Recording,
    meta: RecordingMetadata | None,
    db: AsyncSession,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Return nearest fingerprinted recordings for the same owner.

    A missing fingerprint is data, not an error: the analyst can respond by
    recommending that parameter estimation runs first.
    """

    from ..fingerprints import FingerprintMissing, find_similar_projects

    parsed = SearchSimilarRecordingsArgs.model_validate(args)
    try:
        return await find_similar_projects(db, project, limit=parsed.limit)
    except FingerprintMissing as exc:
        return {
            "project_id": str(project.id),
            "neighbors": [],
            "nearest_distance": None,
            "rare_signal": None,
            "warnings": [str(exc)],
        }


_HANDLERS = {
    "get_project_evidence": _get_project_evidence,
    "run_deep_analysis": _run_deep_analysis,
    "try_demodulation": _try_demodulation,
    "try_fec": _try_fec,
    "search_similar_recordings": _search_similar_recordings,
}

ALLOWED_TOOLS = frozenset(_HANDLERS)


@router.post("/{tool_name}")
async def run_dsp_tool(
    tool_name: str,
    body: InternalToolRequest,
    _token: None = Depends(_require_internal_token),
    db: AsyncSession = Depends(get_db),
):
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")

    project, rec, meta = await _project_bundle(body.project_id, db)
    logger.info(
        "internal dsp tool=%s project=%s args=%s", tool_name, body.project_id, list(body.args)
    )

    try:
        return await handler(project, rec, meta, db, body.args)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("internal dsp tool failed: %s", tool_name)
        raise HTTPException(status_code=422, detail=f"Tool {tool_name} failed: {exc}") from exc
