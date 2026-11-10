from __future__ import annotations

"""Allowlisted DSP tools for the Gemma 4 analyst loop.

The model never chooses a URL or executes code. It can only emit a tool name
from ``TOOL_SPECS`` plus a small, strictly validated argument object. Dispatch
turns that into a private POST to the API's ``/internal/dsp-tools`` route.

Everything here is deliberately boring: no dynamic imports, no eval, no shell.
"""

import json
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from .config import settings

FecType = Literal["convolutional", "reed_solomon", "ldpc", "concatenated"]
ModulationLabel = Literal["BPSK", "QPSK", "8-PSK", "16-QAM", "64-QAM", "2-FSK", "4-FSK"]


class GetProjectEvidenceArgs(BaseModel):
    """No arguments: the project id comes from the signed request."""


class RunDeepAnalysisArgs(BaseModel):
    fec_type: FecType = "convolutional"


class TryDemodulationArgs(BaseModel):
    modulation: ModulationLabel
    samples_per_symbol: int | None = Field(default=None, ge=2, le=64)


class TryFecArgs(BaseModel):
    fec_type: FecType = "convolutional"


class SearchSimilarRecordingsArgs(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)


class ToolSpec(BaseModel):
    name: str
    description: str
    args_model: type[BaseModel]
    parameters: dict[str, Any]


TOOL_SPECS: dict[str, ToolSpec] = {
    "get_project_evidence": ToolSpec(
        name="get_project_evidence",
        description=(
            "Return the project's stored parameter estimates, recording metadata, "
            "and deep-analysis summary. Use this to re-read the current evidence."
        ),
        args_model=GetProjectEvidenceArgs,
        parameters={"type": "object", "properties": {}},
    ),
    "run_deep_analysis": ToolSpec(
        name="run_deep_analysis",
        description=(
            "Re-run deterministic deep analysis over the project ROI with a chosen "
            "FEC decoder. Returns modulation, symbol rate, spectral features, "
            "demodulation summary, de-interleaving score, and FEC verdict."
        ),
        args_model=RunDeepAnalysisArgs,
        parameters={
            "type": "object",
            "properties": {
                "fec_type": {
                    "type": "string",
                    "enum": ["convolutional", "reed_solomon", "ldpc", "concatenated"],
                }
            },
        },
    ),
    "try_demodulation": ToolSpec(
        name="try_demodulation",
        description=(
            "Try a specific modulation/order and return a bit preview plus a "
            "soft-decision margin proxy. Use when the modulation hypothesis is "
            "low confidence or conflicts with the spectrum."
        ),
        args_model=TryDemodulationArgs,
        parameters={
            "type": "object",
            "properties": {
                "modulation": {
                    "type": "string",
                    "enum": ["BPSK", "QPSK", "8-PSK", "16-QAM", "64-QAM", "2-FSK", "4-FSK"],
                },
                "samples_per_symbol": {"type": "integer", "minimum": 2, "maximum": 64},
            },
            "required": ["modulation"],
        },
    ),
    "try_fec": ToolSpec(
        name="try_fec",
        description=(
            "Try a specific FEC decoder (Viterbi, Reed-Solomon, LDPC, or "
            "concatenated) and report whether the frame converged, the CRC "
            "verdict, and corrected-symbol counts."
        ),
        args_model=TryFecArgs,
        parameters={
            "type": "object",
            "properties": {
                "fec_type": {
                    "type": "string",
                    "enum": ["convolutional", "reed_solomon", "ldpc", "concatenated"],
                }
            },
        },
    ),
    "search_similar_recordings": ToolSpec(
        name="search_similar_recordings",
        description=(
            "Search the analyst's own fingerprinted projects for the nearest "
            "spectral neighbours. Returns cosine distances, the rarity "
            "threshold, and a rare-signal candidate flag. Use when the evidence "
            "contains a fingerprint or when the operator asks whether a signal "
            "is novel."
        ),
        args_model=SearchSimilarRecordingsArgs,
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
        },
    ),
}

ALLOWED_TOOLS = frozenset(TOOL_SPECS)


def tool_schemas() -> list[dict[str, Any]]:
    """OpenAI-style function schemas passed to the chat backend."""

    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        }
        for spec in TOOL_SPECS.values()
    ]


TOOL_SCHEMAS = tool_schemas()


def parse_tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Normalise the many shapes a model may use for a tool call."""

    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(call.get("name") or function.get("name") or "")
    if name not in ALLOWED_TOOLS:
        raise ValueError(f"tool not allowlisted: {name or '<missing>'}")

    raw_args: Any = call.get("arguments", function.get("arguments", {}))
    if raw_args is None:
        raw_args = {}
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"tool arguments are not valid JSON: {exc}") from exc
    if not isinstance(raw_args, dict):
        raise ValueError("tool arguments must be a JSON object")
    return name, raw_args


def validate_tool_arguments(name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
    spec = TOOL_SPECS.get(name)
    if spec is None:
        raise ValueError(f"tool not allowlisted: {name}")
    if spec.args_model is GetProjectEvidenceArgs:
        return {}
    return spec.args_model.model_validate(raw_args).model_dump(exclude_none=True)


def _cap_payload(payload: Any, limit_chars: int = 24_000) -> Any:
    """Keep a runaway tool result from blowing up the model context."""

    try:
        encoded = json.dumps(payload, default=str)
    except (TypeError, ValueError):
        return {"error": "tool result was not JSON-serialisable"}
    if len(encoded) <= limit_chars:
        return payload
    return {
        "truncated": True,
        "preview": encoded[:limit_chars],
        "original_chars": len(encoded),
    }


def dispatch_tool(
    call: dict[str, Any],
    project_id: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Validate and execute one allowlisted tool call.

    Failures are returned as data, not raised, so the model can react with a
    second hypothesis instead of the whole insight failing.
    """

    try:
        name, raw_args = parse_tool_call(call)
        args = validate_tool_arguments(name, raw_args)
    except ValueError as exc:
        return {"tool": "invalid", "ok": False, "error": str(exc)}

    url = f"{settings.API_INTERNAL_URL.rstrip('/')}/internal/dsp-tools/{name}"
    body = {"project_id": project_id, "args": args}
    headers = {"X-Internal-Token": settings.INTERNAL_API_TOKEN}

    try:
        if client is not None:
            response = client.post(url, json=body, headers=headers)
        else:
            with httpx.Client(timeout=settings.AI_TOOL_TIMEOUT_SECONDS) as owned:
                response = owned.post(url, json=body, headers=headers)
    except httpx.TimeoutException:
        return {"tool": name, "ok": False, "error": "tool timed out"}
    except httpx.HTTPError as exc:
        return {"tool": name, "ok": False, "error": f"tool request failed: {exc}"}

    if response.status_code >= 400:
        return {
            "tool": name,
            "ok": False,
            "status": response.status_code,
            "error": response.text[:500],
        }

    try:
        result = response.json()
    except ValueError:
        return {"tool": name, "ok": False, "error": "tool returned non-JSON data"}

    return {"tool": name, "ok": True, "result": _cap_payload(result)}
