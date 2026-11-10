from __future__ import annotations

"""Public rare-signal gallery endpoint.

Read-only: fingerprints are built by the deterministic DSP job, never by the AI
sidecar, and the search only looks at the caller's own projects.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..fingerprints import FingerprintMissing, find_similar_projects
from ..models import AnalysisProject, User
from ..schemas import SimilarSignalsResponse

router = APIRouter(prefix="/api/projects", tags=["similar-signals"])


@router.get("/{project_id}/similar", response_model=SimilarSignalsResponse)
async def similar_signals(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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

    try:
        return await find_similar_projects(db, project)
    except FingerprintMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
