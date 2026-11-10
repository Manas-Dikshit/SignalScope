from __future__ import annotations

"""Nearest-neighbour search over stored spectral fingerprints.

The gallery is deliberately scoped to the caller's own projects and honours the
soft-delete flag. Distances are plain cosine distances over a versioned vector,
so the same numbers can be reproduced from the database without a model.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import AnalysisProject, ParameterEstimate, Recording, SignalFingerprint


class FingerprintMissing(LookupError):
    """Raised when a project has no fingerprint yet."""


def _estimate_value(rows: list[ParameterEstimate], name: str) -> Any:
    for row in rows:
        if row.parameter_name == name:
            return (row.value_json or {}).get("value")
    return None


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


async def find_similar_projects(
    db: AsyncSession,
    project: AnalysisProject,
    *,
    limit: int | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Return the nearest fingerprinted projects for ``project``.

    ``rare_signal`` is ``None`` when the gallery has no comparable neighbour yet,
    because "rare" is not provable from a single sample. It is a heuristic
    candidate flag, never an identification.
    """

    from signalscope_dsp.fingerprint import fingerprint_distance

    neighbor_limit = limit or settings.FINGERPRINT_NEIGHBOR_LIMIT
    distance_threshold = float(
        settings.FINGERPRINT_RARE_DISTANCE_THRESHOLD if threshold is None else threshold
    )

    current = (
        await db.execute(
            select(SignalFingerprint).where(SignalFingerprint.project_id == project.id)
        )
    ).scalar_one_or_none()
    if current is None:
        raise FingerprintMissing(
            "No fingerprint for this project yet. Run parameter estimation first."
        )

    rows = (
        await db.execute(
            select(SignalFingerprint, AnalysisProject, Recording)
            .join(AnalysisProject, AnalysisProject.id == SignalFingerprint.project_id)
            .join(Recording, Recording.id == SignalFingerprint.recording_id)
            .where(
                AnalysisProject.created_by == project.created_by,
                AnalysisProject.status != "deleted",
                SignalFingerprint.project_id != project.id,
                SignalFingerprint.version == current.version,
                SignalFingerprint.dimensions == current.dimensions,
            )
        )
    ).all()

    scored: list[dict[str, Any]] = []
    for candidate, candidate_project, candidate_recording in rows:
        distance = fingerprint_distance(current.vector_json, candidate.vector_json)
        scored.append(
            {
                "project_id": str(candidate_project.id),
                "project_name": candidate_project.name,
                "recording_filename": candidate_recording.original_filename,
                "distance": round(distance, 6),
                "similarity": round(max(0.0, 1.0 - distance), 6),
                "_project": candidate_project,
            }
        )
    scored.sort(key=lambda item: item["distance"])
    scored = scored[: max(1, min(int(neighbor_limit), 20))]

    # Attach the neighbour's DSP labels in one query rather than N queries.
    project_ids = [uuid.UUID(item["project_id"]) for item in scored]
    estimates_by_project: dict[uuid.UUID, list[ParameterEstimate]] = {}
    if project_ids:
        estimate_rows = (
            await db.execute(
                select(ParameterEstimate).where(
                    ParameterEstimate.project_id.in_(project_ids),
                    ParameterEstimate.parameter_name.in_(["modulation", "symbol_rate"]),
                )
            )
        ).scalars().all()
        for row in estimate_rows:
            estimates_by_project.setdefault(row.project_id, []).append(row)

    neighbors = []
    for item in scored:
        candidate_project = item.pop("_project")
        candidate_estimates = estimates_by_project.get(candidate_project.id, [])
        item["modulation"] = _estimate_value(candidate_estimates, "modulation")
        item["symbol_rate_hz"] = _estimate_value(candidate_estimates, "symbol_rate")
        neighbors.append(item)

    nearest_distance = neighbors[0]["distance"] if neighbors else None
    if nearest_distance is None:
        rare_signal: bool | None = None
    else:
        rare_signal = bool(nearest_distance > distance_threshold)

    return {
        "project_id": str(project.id),
        "fingerprint": {
            "version": current.version,
            "dimensions": current.dimensions,
            "features": current.features_json or {},
            "created_at": _iso(current.created_at),
        },
        "neighbors": neighbors,
        "nearest_distance": nearest_distance,
        "threshold": distance_threshold,
        "rare_signal": rare_signal,
        "method": (
            "Cosine distance over a shape-normalised PSD embedding plus scalar "
            "spectral features. Similar evidence only, not an identification."
        ),
        "evidence": [
            "Spectra are resampled to normalised frequency so sample rate does not dominate the distance",
            "Distances are computed from the stored fingerprint of each analysis",
        ],
    }
