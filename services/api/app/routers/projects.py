from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import AnalysisProject, ParameterEstimate, Recording, User
from ..schemas import (
    BurstDetectionResponse,
    BurstResponse,
    JobResponse,
    PaginatedResponse,
    ParameterEstimateResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    SegmentInfo,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project_or_403(project: AnalysisProject | None, user_id: uuid.UUID) -> AnalysisProject:
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.created_by != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec_result = await db.execute(select(Recording).where(Recording.id == body.recording_id))
    rec = rec_result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    if rec.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied to recording")

    project = AnalysisProject(
        name=body.name,
        description=body.description,
        recording_id=body.recording_id,
        created_by=user.id,
        selected_start_sample=body.selected_start_sample,
        selected_end_sample=body.selected_end_sample,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    offset: int = 0,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count_q = select(func.count()).select_from(AnalysisProject).where(
        AnalysisProject.created_by == user.id, AnalysisProject.status != "deleted"
    )
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(AnalysisProject)
        .where(AnalysisProject.created_by == user.id, AnalysisProject.status != "deleted")
        .order_by(AnalysisProject.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    items = result.scalars().all()
    return PaginatedResponse(items=items, total=total)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AnalysisProject).where(AnalysisProject.id == project_id))
    project = result.scalar_one_or_none()
    return _project_or_403(project, user.id)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AnalysisProject).where(AnalysisProject.id == project_id))
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(project, field_name, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AnalysisProject).where(AnalysisProject.id == project_id))
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)
    project.status = "deleted"
    await db.commit()


@router.post("/{project_id}/estimate-parameters", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def estimate_parameters(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AnalysisProject).where(AnalysisProject.id == project_id))
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    from ..tasks import estimate_parameters_task

    task = estimate_parameters_task.delay(str(project_id))
    return JobResponse(
        id=task.id,
        status="queued",
        progress_percent=0.0,
        current_stage=None,
        error_message=None,
    )


@router.get("/{project_id}/parameters", response_model=list[ParameterEstimateResponse])
async def list_parameters(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AnalysisProject).where(AnalysisProject.id == project_id))
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    q = (
        select(ParameterEstimate)
        .where(ParameterEstimate.project_id == project_id)
        .order_by(ParameterEstimate.created_at)
    )
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("/{project_id}/detect-bursts", response_model=BurstDetectionResponse)
async def detect_bursts(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AnalysisProject).where(AnalysisProject.id == project_id))
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    rec_result = await db.execute(select(Recording).where(Recording.id == project.recording_id))
    rec = rec_result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    import sys
    from pathlib import Path
    _dsp_root = str(Path(__file__).resolve().parents[3] / "dsp-worker")
    if _dsp_root not in sys.path:
        sys.path.insert(0, _dsp_root)

    from signalscope_dsp.io import load_wav, load_raw_iq, RawIQFormat, load_sigmf
    from signalscope_dsp.detection import detect_bursts as dsp_detect_bursts, burst_stats

    from ..models import RecordingMetadata

    meta_result = await db.execute(select(RecordingMetadata).where(RecordingMetadata.recording_id == rec.id))
    meta = meta_result.scalar_one_or_none()

    loader = rec.file_format
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

    if loader == "wav":
        loaded = load_wav(rec.storage_path, **params)
    elif loader == "raw_iq":
        loaded = load_raw_iq(rec.storage_path, RawIQFormat(**params))
    elif loader == "sigmf":
        loaded = load_sigmf(rec.storage_path)
    else:
        raise HTTPException(status_code=422, detail=f"Unknown format: {loader}")

    samples = loaded.samples
    sr = loaded.metadata.sample_rate.value
    if not sr:
        raise HTTPException(status_code=422, detail="Sample rate unknown; cannot detect bursts")

    if project.selected_start_sample is not None and project.selected_end_sample is not None:
        s = project.selected_start_sample
        e = project.selected_end_sample
        samples = samples[s:e]
        sr_for_detection = sr
    else:
        sr_for_detection = sr

    bursts = dsp_detect_bursts(samples, sr_for_detection)
    stats = burst_stats(bursts)

    burst_responses = [BurstResponse(**b.__dict__) for b in bursts]
    stats_ser = {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in stats.items()}
    return BurstDetectionResponse(bursts=burst_responses, stats=stats_ser)


@router.get("/{project_id}/segments", response_model=list[SegmentInfo])
async def get_segments(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AnalysisProject).where(AnalysisProject.id == project_id))
    project = result.scalar_one_or_none()
    _project_or_403(project, user.id)

    rec_result = await db.execute(select(Recording).where(Recording.id == project.recording_id))
    rec = rec_result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    meta_result = await db.execute(select(RecordingMetadata).where(RecordingMetadata.recording_id == rec.id))
    meta = meta_result.scalar_one_or_none()
    sr = meta.sample_rate if meta else None

    total = rec.total_samples or 0
    start = project.selected_start_sample or 0
    end = project.selected_end_sample or total
    dur = (end - start) / sr if sr else None
    return [SegmentInfo(start_sample=start, end_sample=end, duration_seconds=dur)]
