from __future__ import annotations

from .backend import get_backend
from .config import settings
from .schemas import InsightRequest, InsightResponse
from .validation import render_template, validate_insight


def run_analyst(request: InsightRequest) -> InsightResponse:
    """Generate one validated analyst brief.

    Phase 0/1 is one-shot: no tool loop yet. The model sees the evidence bundle
    and returns a cited structure. Phase 2 adds the allowlisted DSP tool loop.
    """

    backend = get_backend()
    raw = backend.generate(request)
    response = validate_insight(raw, request.evidence)
    response.summary = render_template(response.summary_template, request.evidence)
    response.model_name = settings.AI_MODEL if backend.name != "fake" else "fake-backend"
    response.prompt_version = request.prompt_version or settings.AI_PROMPT_VERSION
    return response
