from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import AnalysisProject, Recording, User
from ..schemas import PaginatedResponse, ProjectResponse, RecordingResponse

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def dashboard_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec_count = (
        await db.execute(
            select(func.count())
            .select_from(Recording)
            .where(Recording.uploaded_by == user.id, Recording.status != "deleted")
        )
    ).scalar() or 0

    proj_count = (
        await db.execute(
            select(func.count())
            .select_from(AnalysisProject)
            .where(AnalysisProject.created_by == user.id, AnalysisProject.status != "deleted")
        )
    ).scalar() or 0

    recent_recs = (
        await db.execute(
            select(Recording)
            .where(Recording.uploaded_by == user.id, Recording.status != "deleted")
            .order_by(Recording.created_at.desc())
            .limit(5)
        )
    ).scalars().all()

    recent_projects = (
        await db.execute(
            select(AnalysisProject)
            .where(AnalysisProject.created_by == user.id, AnalysisProject.status != "deleted")
            .order_by(AnalysisProject.created_at.desc())
            .limit(5)
        )
    ).scalars().all()

    return {
        "recording_count": rec_count,
        "project_count": proj_count,
        "recent_recordings": [RecordingResponse.model_validate(r) for r in recent_recs],
        "recent_projects": [ProjectResponse.model_validate(p) for p in recent_projects],
        "running_jobs": [],
    }
