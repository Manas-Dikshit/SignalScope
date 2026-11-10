from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .agent import run_analyst
from .config import settings
from .schemas import InsightRequest, InsightResponse

app = FastAPI(title="SignalScope AI", version="0.1.0")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "backend": settings.AI_BACKEND,
        "model": settings.AI_MODEL,
        "prompt_version": settings.AI_PROMPT_VERSION,
    }


@app.post("/v1/insight", response_model=InsightResponse)
def insight(request: InsightRequest) -> InsightResponse:
    try:
        return run_analyst(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # model/runtime failure
        raise HTTPException(status_code=502, detail=f"AI generation failed: {exc}") from exc
