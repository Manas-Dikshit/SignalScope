from __future__ import annotations

import re
from typing import Any

from .schemas import InsightResponse
from .tools import ALLOWED_TOOLS

_PLACEHOLDER = re.compile(r"\{\{estimate:([A-Za-z0-9_]+)\}\}")


def evidence_estimate_names(evidence: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in evidence.get("estimates", []) or []:
        if isinstance(item, dict) and item.get("name"):
            names.add(str(item["name"]))
    for key in ("modulation", "symbol_rate", "symbol_rate_hz", "fec", "constellation", "snr_db"):
        if key in evidence:
            names.add(key)
    deep = evidence.get("deep_analysis") or {}
    if isinstance(deep, dict):
        for key in ("modulation", "symbol_rate", "symbol_rate_hz", "fec", "constellation"):
            if key in deep:
                names.add(key)
    return names


def _format_value(value: Any, unit: str | None = None) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        if abs(value) >= 1000:
            text = f"{value:,.1f}".rstrip("0").rstrip(".")
        else:
            text = f"{value:,.4g}"
    else:
        text = str(value)
    return f"{text} {unit}".strip() if unit else text


def render_template(template: str, evidence: dict[str, Any]) -> str:
    """Substitute only backend-owned evidence values into the model template.

    The model never writes a numeric value itself: it emits a placeholder and the
    server fills it from provenance. Unknown placeholders are made explicit
    instead of being guessed.
    """

    by_name: dict[str, dict[str, Any]] = {}
    for item in evidence.get("estimates", []) or []:
        if isinstance(item, dict) and item.get("name"):
            by_name[str(item["name"])] = item

    deep = evidence.get("deep_analysis") or {}
    if isinstance(deep, dict):
        if "symbol_rate_hz" in deep:
            by_name.setdefault("symbol_rate", {"value": deep["symbol_rate_hz"], "unit": "Hz"})

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        item = by_name.get(name)
        if not item:
            return f"[unknown:{name}]"
        return _format_value(item.get("value"), item.get("unit"))

    return _PLACEHOLDER.sub(repl, template).strip()


def validate_tool_trace(trace: list[dict[str, Any]]) -> None:
    """Every executed tool must be on the allowlist (defence in depth)."""

    for entry in trace:
        name = entry.get("tool")
        if not name and isinstance(entry.get("call"), dict):
            name = entry["call"].get("name")
        if name not in ALLOWED_TOOLS:
            raise ValueError(f"tool trace contains non-allowlisted tool: {name or '<missing>'}")


def validate_insight(
    payload: dict[str, Any],
    evidence: dict[str, Any],
    tool_trace: list[dict[str, Any]] | None = None,
) -> InsightResponse:
    """Validate shape, citations, placeholders, and tool usage.

    Raises ``ValueError`` on a dishonest or malformed response so the caller can
    retry or fall back to a deterministic brief.
    """

    response = InsightResponse.model_validate(payload)
    known = evidence_estimate_names(evidence)

    # When there is no evidence at all, the honest brief is "run estimation
    # first" with no citations. Skip citation checks only in that case.
    if known:
        for match in _PLACEHOLDER.finditer(response.summary_template):
            name = match.group(1)
            if name not in known:
                raise ValueError(f"summary_template references unknown evidence: {name}")

        if not response.citations:
            raise ValueError("insight has no citations")

        for ref in response.citations:
            if ref not in known:
                raise ValueError(f"citation references unknown evidence: {ref}")

        for ref in response.hypothesis.evidence_refs:
            if ref not in known:
                raise ValueError(f"hypothesis references unknown evidence: {ref}")

    if tool_trace is not None:
        validate_tool_trace(tool_trace)
        response.tool_trace = tool_trace

    return response
