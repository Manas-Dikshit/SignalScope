from __future__ import annotations

from typing import Any

import httpx

from .config import settings


def _payload(project_id: str, evidence: dict[str, Any], images: dict[str, str] | None = None) -> dict:
    return {
        "project_id": project_id,
        "prompt_version": settings.AI_PROMPT_VERSION,
        "evidence": evidence,
        "images": images or {},
    }


def request_insight_sync(
    project_id: str,
    evidence: dict[str, Any],
    images: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Call the local Gemma 4 sidecar from a Celery worker."""
    url = f"{settings.AI_SERVICE_URL.rstrip('/')}/v1/insight"
    with httpx.Client(timeout=settings.AI_TIMEOUT_SECONDS) as client:
        response = client.post(url, json=_payload(project_id, evidence, images))
        response.raise_for_status()
        return response.json()


async def request_insight(
    project_id: str,
    evidence: dict[str, Any],
    images: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Call the local Gemma 4 sidecar from async API code."""
    url = f"{settings.AI_SERVICE_URL.rstrip('/')}/v1/insight"
    async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
        response = await client.post(url, json=_payload(project_id, evidence, images))
        response.raise_for_status()
        return response.json()
