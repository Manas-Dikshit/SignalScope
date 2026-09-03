from __future__ import annotations

import hashlib
import json
import math
import shutil
import uuid
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Recording, RecordingMetadata, User
from ..schemas import (
    PaginatedResponse,
    PreviewResponse,
    RecordingMetadataResponse,
    RecordingMetadataUpdate,
    RecordingResponse,
    RecordingUploadResponse,
    RawIQParams,
    WavParams,
)

router = APIRouter(prefix="/api/recordings", tags=["recordings"])

# ── DSP loaders (imported lazily in the validation call) ──────────────────────

import sys
from pathlib import Path

_dsp_root = str(Path(__file__).resolve().parents[3] / "dsp-worker")
if _dsp_root not in sys.path:
    sys.path.insert(0, _dsp_root)

from signalscope_dsp.io import load_wav, load_raw_iq, RawIQFormat, load_sigmf  # noqa: E402


async def _validate_and_load(path: str, loader: str, params: dict):
    """Try loading the file with the DSP loader to validate it. Returns the Recording."""
    if loader == "wav":
        return load_wav(path, stereo_mode=params.get("stereo_mode", "left_is_i_right_is_q"))
    elif loader == "raw_iq":
        fmt = RawIQFormat(
            dtype=params.get("dtype", "int16"),
            layout=params.get("layout", "interleaved"),
            endian=params.get("endian", "little"),
            signed_offset=params.get("signed_offset", True),
            sample_rate_hz=params.get("sample_rate_hz"),
            center_frequency_hz=params.get("center_frequency_hz"),
        )
        return load_raw_iq(path, fmt)
    elif loader == "sigmf":
        return load_sigmf(path)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown loader: {loader}")


def _persist_metadata(db: AsyncSession, recording_id: uuid.UUID, rec):
    """Write DSP RecordingMetadata into recording_metadata table."""
    m = rec.metadata
    entry = RecordingMetadata(
        recording_id=recording_id,
        sample_rate=m.sample_rate.value if m.sample_rate else None,
        center_frequency=m.center_frequency.value if m.center_frequency else None,
        data_type=m.sample_dtype,
        iq_layout=m.extra.get("layout"),
        endian=m.extra.get("endian"),
        channel_count=m.channel_count,
        sample_width=m.sample_dtype,
        is_complex=m.is_complex,
        metadata_source=m.sample_rate.source.value if m.sample_rate else None,
        metadata_confidence=m.sample_rate.confidence if m.sample_rate else None,
        raw_metadata_json=m.extra,
    )
    db.add(entry)


@router.post("/upload", response_model=RecordingUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_recording(
    file: UploadFile = File(...),
    loader: str = Form("wav"),
    raw_iq_params: str = Form("{}"),
    wav_params: str = Form("{}"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Read and hash
    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    file_hash = hashlib.sha256(contents).hexdigest()

    # Duplicate check for this user
    existing = await db.execute(
        select(Recording).where(Recording.file_hash == file_hash, Recording.uploaded_by == user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate file already uploaded")

    # Persist to disk
    rec_id = uuid.uuid4()
    upload_dir = Path(settings.DATA_DIR) / "uploads" / str(user.id) / str(rec_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = upload_dir / file.filename
    storage_path.write_bytes(contents)

    # Validate with DSP loader
    params = json.loads(raw_iq_params) if loader == "raw_iq" else json.loads(wav_params) if loader == "wav" else {}
    try:
        rec = await _validate_and_load(str(storage_path), loader, params)
    except Exception as exc:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"File validation failed: {exc}")

    file_format = loader
    recording = Recording(
        id=rec_id,
        original_filename=file.filename,
        storage_path=str(storage_path),
        file_hash=file_hash,
        file_size=len(contents),
        file_format=file_format,
        uploaded_by=user.id,
        status="uploaded",
        duration_seconds=rec.duration_s(),
        total_samples=rec.metadata.total_samples,
    )
    db.add(recording)
    await db.flush()
    _persist_metadata(db, rec_id, rec)
    await db.commit()
    await db.refresh(recording)
    return recording


@router.get("", response_model=PaginatedResponse[RecordingResponse])
async def list_recordings(
    offset: int = 0,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count_q = select(func.count()).select_from(Recording).where(
        Recording.uploaded_by == user.id, Recording.status != "deleted"
    )
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Recording)
        .where(Recording.uploaded_by == user.id, Recording.status != "deleted")
        .order_by(Recording.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    items = result.scalars().all()
    return PaginatedResponse(items=items, total=total)


@router.get("/{recording_id}", response_model=RecordingResponse)
async def get_recording(
    recording_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return rec


@router.patch("/{recording_id}/metadata", response_model=RecordingMetadataResponse)
async def update_metadata(
    recording_id: uuid.UUID,
    body: RecordingMetadataUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    meta_result = await db.execute(select(RecordingMetadata).where(RecordingMetadata.recording_id == recording_id))
    meta = meta_result.scalar_one_or_none()
    if not meta:
        raise HTTPException(status_code=404, detail="Recording metadata not found")

    update_data = body.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(meta, field_name, value)
    await db.commit()
    await db.refresh(meta)
    return meta


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recording(
    recording_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    rec.status = "deleted"
    await db.commit()


@router.get("/{recording_id}/preview", response_model=PreviewResponse)
async def preview_recording(
    recording_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    meta_result = await db.execute(select(RecordingMetadata).where(RecordingMetadata.recording_id == recording_id))
    meta = meta_result.scalar_one_or_none()

    try:
        loader = rec.file_format
        path = rec.storage_path
        params: dict = {}
        if meta and meta.raw_metadata_json:
            if loader == "raw_iq":
                params = {
                    "dtype": meta.data_type or "int16",
                    "layout": meta.iq_layout or "interleaved",
                    "endian": meta.endian or "little",
                    "sample_rate_hz": meta.sample_rate,
                    "center_frequency_hz": meta.center_frequency,
                }
            elif loader == "wav":
                params = {"stereo_mode": meta.raw_metadata_json.get("stereo_mode", "left_is_i_right_is_q")}
        loaded = await _validate_and_load(path, loader, params)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not load recording for preview")

    n = min(10000, len(loaded.samples))
    samples = loaded.samples[:n]
    stats_dict = {
        "peak_amplitude": float(np.max(np.abs(samples))) if len(samples) > 0 else 0.0,
        "rms_amplitude": float(np.sqrt(np.mean(np.abs(samples) ** 2))) if len(samples) > 0 else 0.0,
    }
    return PreviewResponse(
        samples_real=[float(x) for x in samples.real],
        samples_imag=[float(x) for x in samples.imag],
        sample_rate=meta.sample_rate if meta else None,
        total_samples=rec.total_samples or 0,
        preview_count=n,
        stats=stats_dict,
    )
