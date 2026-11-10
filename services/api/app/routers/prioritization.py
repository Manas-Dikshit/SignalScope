from __future__ import annotations

"""Scientific candidate queue for celestial astronomical signals.

Read-only ranking of the caller's analysed projects by novelty,
repeatability, astrophysical plausibility, and follow-up feasibility.
All inputs come from stored fingerprints, estimates, and metadata —
no recording is re-read, and nothing is ranked across users.
"""

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    AnalysisProject,
    ParameterEstimate,
    Recording,
    RecordingMetadata,
    SignalFingerprint,
    User,
)
from ..prioritization import EVIDENCE, METHOD, CandidateFacts, prioritize
from ..schemas import PrioritizedCandidatesResponse

router = APIRouter(prefix="/api/candidates", tags=["prioritization"])


def _pairwise_distances(
    fingerprints: list[SignalFingerprint],
) -> dict[uuid.UUID, list[float]]:
    """Cosine distance from each fingerprint to every comparable one.

    Fingerprints only compare within the same version and dimensionality,
    matching the rare-signal gallery rule. A few hundred candidates are
    trivial at 22 dimensions, so an in-process matrix beats a vector store.
    """
    from signalscope_dsp.fingerprint import fingerprint_distance

    groups: dict[tuple[str, int], list[SignalFingerprint]] = defaultdict(list)
    for fp in fingerprints:
        groups[(fp.version, fp.dimensions)].append(fp)

    distances: dict[uuid.UUID, list[float]] = defaultdict(list)
    for members in groups.values():
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                d = fingerprint_distance(a.vector_json, b.vector_json)
                distances[a.project_id].append(d)
                distances[b.project_id].append(d)
    return distances


@router.get("/prioritized", response_model=PrioritizedCandidatesResponse)
async def prioritized_candidates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    threshold: float | None = None,
):
    from ..config import settings

    repeat_threshold = float(
        settings.FINGERPRINT_RARE_DISTANCE_THRESHOLD if threshold is None else threshold
    )

    rows = (
        await db.execute(
            select(AnalysisProject, Recording)
            .join(Recording, Recording.id == AnalysisProject.recording_id)
            .where(
                AnalysisProject.created_by == user.id,
                AnalysisProject.status != "deleted",
            )
            .order_by(AnalysisProject.created_at.desc())
        )
    ).all()

    project_ids = [project.id for project, _ in rows]
    if not project_ids:
        return PrioritizedCandidatesResponse(
            threshold=repeat_threshold, candidates=[], method=METHOD, evidence=EVIDENCE
        )

    recording_ids = {rec.id for _, rec in rows}
    metadata_rows = (
        await db.execute(
            select(RecordingMetadata).where(RecordingMetadata.recording_id.in_(recording_ids))
        )
    ).scalars().all()
    metadata_by_recording = {m.recording_id: m for m in metadata_rows}

    fingerprints = (
        await db.execute(
            select(SignalFingerprint).where(SignalFingerprint.project_id.in_(project_ids))
        )
    ).scalars().all()
    distance_map = _pairwise_distances(list(fingerprints))
    fingerprint_by_project = {fp.project_id: fp for fp in fingerprints}

    estimate_rows = (
        await db.execute(
            select(ParameterEstimate)
            .where(ParameterEstimate.project_id.in_(project_ids))
            .order_by(ParameterEstimate.created_at)
        )
    ).scalars().all()
    # Deep-analysis runs accumulate estimates; the newest row per parameter
    # name is the current view, matching how the workspace renders them.
    estimates_by_project: dict[uuid.UUID, dict[str, dict]] = defaultdict(dict)
    for row in estimate_rows:
        value = dict(row.value_json or {})
        value["confidence"] = row.confidence
        estimates_by_project[row.project_id][row.parameter_name] = value

    facts: list[CandidateFacts] = []
    for project, recording in rows:
        estimates = estimates_by_project.get(project.id, {})
        if not estimates:
            # Never analysed: nothing to prioritize yet.
            continue
        fp = fingerprint_by_project.get(project.id)
        others = distance_map.get(project.id, [])
        meta = metadata_by_recording.get(recording.id)
        facts.append(
            CandidateFacts(
                project_id=str(project.id),
                project_name=project.name,
                created_at=project.created_at.isoformat() if project.created_at else None,
                features=dict(fp.features_json or {}) if fp else {},
                estimates=estimates,
                gallery_size=len(others),
                nearest_distance=min(others) if others else None,
                repeat_count=sum(1 for d in others if d <= repeat_threshold),
                duration_seconds=recording.duration_seconds,
                center_frequency_hz=meta.center_frequency if meta else None,
            )
        )

    ranked = prioritize(facts, repeat_threshold)
    return PrioritizedCandidatesResponse(
        threshold=repeat_threshold, candidates=ranked, method=METHOD, evidence=EVIDENCE
    )
