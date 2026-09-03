from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import JobResponse
from ..tasks import celery_app

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    result = celery_app.AsyncResult(job_id)

    if result.state == "PENDING":
        return JobResponse(id=job_id, status="queued", progress_percent=0.0, current_stage=None, error_message=None)
    elif result.state == "STARTED":
        meta = result.info if isinstance(result.info, dict) else {}
        return JobResponse(
            id=job_id,
            status="running",
            progress_percent=meta.get("progress_percent", 0.0),
            current_stage=meta.get("current_stage"),
            error_message=None,
        )
    elif result.state == "SUCCESS":
        return JobResponse(id=job_id, status="completed", progress_percent=100.0, current_stage=None, error_message=None)
    elif result.state == "FAILURE":
        error_msg = str(result.info) if result.info else "Unknown error"
        return JobResponse(id=job_id, status="failed", progress_percent=0.0, current_stage=None, error_message=error_msg)
    else:
        return JobResponse(id=job_id, status=result.state.lower(), progress_percent=0.0, current_stage=None, error_message=None)
