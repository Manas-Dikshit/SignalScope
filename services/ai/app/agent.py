from __future__ import annotations

import json
import re
from typing import Any, Callable

from .backend import deterministic_payload, get_backend
from .config import settings
from .prompts import SYSTEM_PROMPT, TOOL_CALL_INSTRUCTIONS, evidence_prompt
from .schemas import InsightRequest, InsightResponse
from .tools import TOOL_SCHEMAS, dispatch_tool, parse_tool_call
from .validation import render_template, validate_insight

MAX_STEPS = settings.AI_MAX_TOOL_STEPS
MAX_TOOL_CALLS = 8

Dispatcher = Callable[[dict[str, Any], str], dict[str, Any]]


def build_messages(request: InsightRequest) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n" + TOOL_CALL_INSTRUCTIONS},
        {
            "role": "user",
            "content": evidence_prompt(
                json.dumps(request.evidence, indent=2, default=str),
                list((request.images or {}).keys()),
            ),
        },
    ]


def _extract_payload(out: dict[str, Any]) -> dict[str, Any]:
    content = out.get("content", out)
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("model did not return a JSON object")
        payload = json.loads(match.group(0))
        if isinstance(payload, dict):
            return payload
    raise ValueError("model did not return an insight object")


def _call_id(call: dict[str, Any], index: int) -> str:
    return str(call.get("id") or f"call_{index}")


def run_analyst(
    request: InsightRequest,
    *,
    dispatch: Dispatcher | None = None,
) -> InsightResponse:
    """Run the allowlisted tool loop, then validate one cited brief.

    The model can only request tools from ``TOOL_SCHEMAS``. Each call is
    validated, executed through the private API route, and recorded in
    ``tool_trace``. ``MAX_STEPS`` and ``MAX_TOOL_CALLS`` bound the loop so a
    confused model cannot keep the worker busy.
    """

    backend = get_backend()
    dispatcher = dispatch or dispatch_tool
    messages = build_messages(request)
    trace: list[dict[str, Any]] = []
    tool_calls_made = 0

    for _ in range(MAX_STEPS):
        out = backend.chat(messages, tools=TOOL_SCHEMAS, request=request)
        calls = out.get("tool_calls") or []
        if not calls or tool_calls_made >= MAX_TOOL_CALLS:
            break

        for index, call in enumerate(calls):
            if tool_calls_made >= MAX_TOOL_CALLS:
                break
            tool_calls_made += 1

            try:
                name, raw_args = parse_tool_call(call)
                result = dispatcher(call, request.project_id)
            except ValueError as exc:
                name, raw_args = "invalid", {}
                result = {"tool": "invalid", "ok": False, "error": str(exc)}

            call_id = _call_id(call, index)
            trace.append({"tool": name, "arguments": raw_args, "result": result})
            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "tool_calls": [
                                {
                                    "id": call_id,
                                    "name": name,
                                    "arguments": raw_args,
                                }
                            ]
                        }
                    ),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": json.dumps(result, default=str),
                }
            )

    final = backend.chat(messages, response_format={"type": "insight"}, request=request)
    payload = _extract_payload(final)

    try:
        response = validate_insight(payload, request.evidence, tool_trace=trace)
    except ValueError as first_error:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Your previous response failed validation: "
                    f"{first_error}. Return corrected JSON only."
                ),
            }
        )
        retry = backend.chat(messages, response_format={"type": "insight"}, request=request)
        try:
            response = validate_insight(
                _extract_payload(retry), request.evidence, tool_trace=trace
            )
        except ValueError as second_error:
            fallback = deterministic_payload(request.evidence)
            fallback["limitations"] = list(fallback.get("limitations", [])) + [
                f"Model output rejected: {second_error}"
            ]
            response = validate_insight(fallback, request.evidence, tool_trace=trace)

    response.summary = render_template(response.summary_template, request.evidence)
    response.model_name = settings.AI_MODEL if backend.name != "fake" else "fake-backend"
    response.prompt_version = request.prompt_version or settings.AI_PROMPT_VERSION
    return response
