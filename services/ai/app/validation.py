from __future__ import annotations

import re
from typing import Any

from .schemas import InsightResponse

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


def validate_insight(payload: dict[str, Any], evidence: dict[str, Any]) -> InsightResponse:
    """Validate shape, citations, and placeholder references.

    Raises ``ValueError`` on a dishonest or malformed response so the caller can
    retry or fall back to a deterministic brief.
    """

    response = InsightResponse.model_validate(payload)
    known = evidence_estimate_names(evidence)

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

    return response
