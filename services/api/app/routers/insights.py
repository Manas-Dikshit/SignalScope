from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import AnalysisInsight, AnalysisProject, User
from ..schemas import AnalysisInsightResponse, JobResponse

router = APIRouter(prefix="/api/projects", tags=["insights"])


async def _owned_project(
    project_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> AnalysisProject:
    result = await db.execute(
        select(AnalysisProject).where(
            AnalysisProject.id == project_id,
            AnalysisProject.status != "deleted",
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.created_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return project


@router.post(
    "/{project_id}/insights",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_insight(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(project_id, user, db)
    if not settings.AI_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI insights are disabled. Set AI_ENABLED=true and start the ai service.",
        )

    from ..tasks import generate_insight_task

    task = generate_insight_task.delay(str(project_id))
    return JobResponse(
        id=task.id,
        status="queued",
        progress_percent=0.0,
        current_stage=None,
        error_message=None,
    )


@router.get("/{project_id}/insights", response_model=AnalysisInsightResponse)
async def latest_insight(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project(project_id, user, db)
    result = await db.execute(
        select(AnalysisInsight)
        .where(AnalysisInsight.project_id == project_id)
        .order_by(AnalysisInsight.created_at.desc())
        .limit(1)
    )
    insight = result.scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail="No insight generated yet")
    return insight
