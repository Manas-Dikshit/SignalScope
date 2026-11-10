from __future__ import annotations

import json
import re
from typing import Any, Protocol

from .config import settings
from .prompts import SYSTEM_PROMPT, TOOL_CALL_INSTRUCTIONS, evidence_prompt
from .schemas import InsightRequest

LOW_CONFIDENCE_MODULATION = 0.6
_SUPPORTED_LABELS = {"BPSK", "QPSK", "8-PSK", "16-QAM", "64-QAM", "2-FSK", "4-FSK"}


class InsightBackend(Protocol):
    name: str

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        request: InsightRequest | None = None,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        ...


def _estimate_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in evidence.get("estimates", []) or []:
        if isinstance(item, dict) and item.get("name"):
            out[str(item["name"])] = item
    deep = evidence.get("deep_analysis") or {}
    if isinstance(deep, dict):
        if deep.get("symbol_rate_hz") is not None:
            out.setdefault("symbol_rate", {"value": deep["symbol_rate_hz"], "unit": "Hz"})
    return out


def deterministic_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    """Build a cited brief without a language model.

    Used by the fake backend and as the validation fallback. It only restates
    evidence values through placeholders, so it cannot invent a number.
    """

    estimates = _estimate_map(evidence)
    modulation = estimates.get("modulation", {})
    symbol_rate = estimates.get("symbol_rate", {})
    snr = estimates.get("snr_db", {})

    mod_label = modulation.get("value") or "unknown"
    mod_conf = modulation.get("confidence")
    citations: dict[str, str] = {}
    if modulation:
        citations["modulation"] = "parameter_estimates.modulation"
    if symbol_rate:
        citations["symbol_rate"] = "parameter_estimates.symbol_rate"
    if snr:
        citations["snr_db"] = "parameter_estimates.snr_db"

    if modulation and symbol_rate:
        summary = (
            "DSP evidence currently supports {{estimate:modulation}} at "
            "{{estimate:symbol_rate}}. The estimate is a hypothesis, not a "
            "guarantee; review the linked provenance before acting on it."
        )
    elif modulation:
        summary = (
            "DSP evidence currently supports {{estimate:modulation}}. The "
            "estimate is a hypothesis, not a guarantee; review the linked "
            "provenance before acting on it."
        )
    elif symbol_rate:
        summary = (
            "DSP evidence shows activity at {{estimate:symbol_rate}}. The "
            "estimate is a hypothesis, not a guarantee; review the linked "
            "provenance before acting on it."
        )
    else:
        summary = "No DSP estimates are available yet. Run parameter estimation first."

    anomalies: list[dict[str, Any]] = []
    for item in evidence.get("estimates", []) or []:
        for warning in item.get("warnings", []) or []:
            anomalies.append(
                {
                    "description": str(warning),
                    "severity": "low",
                    "evidence_refs": [str(item.get("name", "unknown"))],
                }
            )

    return {
        "summary_template": summary,
        "hypothesis": {
            "label": str(mod_label),
            "agreement_with_dsp": None,
            "confidence_note": f"Source confidence: {mod_conf}" if mod_conf is not None else "",
            "evidence_refs": [k for k in ("modulation", "symbol_rate") if k in citations],
        },
        "conflicts": [],
        "anomalies": anomalies,
        "recommended_actions": [],
        "unknowns": (
            ["AI reasoning is running in fake/fallback mode until a local Gemma 4 model is loaded."]
            if not citations
            else []
        ),
        "limitations": [
            "AI-generated hypothesis. Verify against the DSP evidence.",
            "Deterministic fallback: no language model was invoked.",
        ],
        "citations": citations,
        "tool_trace": [],
    }


def _with_visual_note(payload: dict[str, Any], images: dict[str, str] | None) -> dict[str, Any]:
    if not images:
        return payload
    payload = dict(payload)
    payload["limitations"] = list(payload.get("limitations", [])) + [
        "Visual second opinion reviewed: " + ", ".join(sorted(images)) + "."
    ]
    hypothesis = dict(payload.get("hypothesis") or {})
    note = str(hypothesis.get("confidence_note") or "").strip()
    visual = "Visual evidence reviewed: " + ", ".join(sorted(images)) + "."
    hypothesis["confidence_note"] = (note + " " + visual).strip()
    payload["hypothesis"] = hypothesis
    return payload


def _tool_was_called(messages: list[dict[str, Any]], name: str | None = None) -> bool:
    for message in messages:
        if message.get("role") != "tool":
            continue
        if name is None or message.get("name") == name:
            return True
    return False


def _tool_result(messages: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Return the inner payload of the last successful tool call, if any."""

    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("name") != name:
            continue
        content = message.get("content")
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        inner = parsed.get("result")
        return inner if isinstance(inner, dict) else None
    return None


def _with_similarity_note(
    payload: dict[str, Any], similar: dict[str, Any] | None
) -> dict[str, Any]:
    """Explain a gallery lookup without asserting a measurement.

    The rare-signal flag is a heuristic over backend-provided distances, so the
    wording stays comparative ("farther than the threshold") and never claims an
    identification.
    """

    if not similar:
        return payload

    payload = dict(payload)
    anomalies = list(payload.get("anomalies") or [])
    limitations = list(payload.get("limitations") or [])

    rare = similar.get("rare_signal")
    if rare is True:
        anomalies.append(
            {
                "description": (
                    "The nearest gallery neighbour is farther than the similarity "
                    "threshold, so this recording is a rare-signal candidate."
                ),
                "severity": "low",
                "evidence_refs": ["similar_recordings"],
            }
        )
    elif rare is False:
        limitations.append(
            "A similar recording exists in the gallery; novelty is not claimed."
        )
    else:
        limitations.append(
            "No comparable gallery neighbours are available yet, so novelty "
            "cannot be assessed."
        )

    limitations.append(
        "Similarity is a cosine distance over stored spectral fingerprints, "
        "not an identification of a transmitter."
    )
    payload["anomalies"] = anomalies
    payload["limitations"] = limitations
    return payload


def _fake_modulation_candidate(evidence: dict[str, Any]) -> str | None:
    estimates = _estimate_map(evidence)
    modulation = estimates.get("modulation") or {}
    confidence = modulation.get("confidence")
    if confidence is None or float(confidence) >= LOW_CONFIDENCE_MODULATION:
        return None

    for alt in modulation.get("alternatives", []) or []:
        label = str(alt.get("label") or "") if isinstance(alt, dict) else ""
        if label in _SUPPORTED_LABELS:
            return label

    current = str(modulation.get("value") or "").upper()
    for label in ("QPSK", "BPSK", "16-QAM", "2-FSK"):
        if label != current:
            return label
    return None


class FakeBackend:
    """Deterministic backend used for tests, UI work, and the no-model fallback.

    It implements the same chat/tool protocol as a real model. When the DSP
    modulation confidence is low it emits exactly one follow-up
    ``try_demodulation`` call, which is enough to exercise the Phase 2 loop in
    CI and in judge demos without downloading weights.
    """

    name = "fake"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        request: InsightRequest | None = None,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        evidence = request.evidence if request is not None else {}

        if tools and not _tool_was_called(messages, "try_demodulation"):
            candidate = _fake_modulation_candidate(evidence)
            if candidate:
                arguments: dict[str, Any] = {"modulation": candidate}
                estimates = _estimate_map(evidence)
                sample_rate = (evidence.get("recording") or {}).get("sample_rate_hz")
                symbol_rate = (estimates.get("symbol_rate") or {}).get("value")
                if sample_rate and symbol_rate:
                    sps = int(round(float(sample_rate) / float(symbol_rate)))
                    arguments["samples_per_symbol"] = max(2, min(64, sps))
                return {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "name": "try_demodulation",
                            "arguments": arguments,
                        }
                    ]
                }

        # A stored fingerprint means a gallery lookup is possible. The fake
        # backend performs exactly one lookup so the Phase 4 loop is exercised
        # deterministically, then explains the result without inventing numbers.
        if (
            tools
            and evidence.get("fingerprint")
            and not evidence.get("similar_recordings")
            and not _tool_was_called(messages, "search_similar_recordings")
        ):
            return {
                "tool_calls": [
                    {
                        "id": "call_similar",
                        "name": "search_similar_recordings",
                        "arguments": {"limit": 5},
                    }
                ]
            }

        return {
            "content": _with_similarity_note(
                _with_visual_note(deterministic_payload(evidence), request.images),
                _tool_result(messages, "search_similar_recordings"),
            )
        }

    def generate(self, request: InsightRequest) -> dict[str, Any]:
        return _with_visual_note(
            deterministic_payload(request.evidence or {}), request.images
        )


class TransformersBackend:
    """Local Gemma 4 backend using Hugging Face Transformers.

    Model loading stays lazy so the API process and tests never import
    torch/transformers. The chat method accepts OpenAI-style tool schemas and
    parses either a tool-call object or the final InsightResponse JSON.
    """

    name = "transformers"

    def __init__(self) -> None:
        self._model = None
        self._processor = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForMultimodalLM, AutoProcessor
        except ImportError as exc:  # pragma: no cover - depends on optional deps
            raise RuntimeError(
                "transformers backend selected but optional AI dependencies are not installed"
            ) from exc

        load_kwargs: dict[str, Any] = {"device_map": settings.AI_DEVICE}
        quantization = settings.AI_QUANTIZATION.strip().lower()
        if quantization in {"4bit", "8bit"}:
            from transformers import BitsAndBytesConfig

            load_kwargs["dtype"] = torch.bfloat16
            if quantization == "4bit":
                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    # Gemma 4 E2B is multimodal: the vision/audio encoders stay
                    # in fp32 and spill to CPU when the quantized core won't fit
                    # in a 6 GB consumer GPU.
                    llm_int8_enable_fp32_cpu_offload=True,
                )
            else:
                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_8bit=True,
                    llm_int8_enable_fp32_cpu_offload=True,
                )
        else:
            load_kwargs["dtype"] = "auto"

        if settings.AI_MAX_GPU_MEMORY:
            # Cap the accelerator and let accelerate spill overflow layers
            # (fp32 vision/audio encoders) to CPU instead of exceeding VRAM.
            load_kwargs["max_memory"] = {
                0: settings.AI_MAX_GPU_MEMORY,
                "cpu": "24GiB",
            }
        else:
            # Conservative default for consumer GPUs (e.g. RTX 3050 6 GB):
            # leave room for the quantized core + fp32 multimodal encoders.
            load_kwargs["max_memory"] = {
                0: "4GiB",
                "cpu": "24GiB",
            }
        # device_map stays "auto" so accelerate decides placement; do not force
        # everything onto GPU 0, which creates meta tensors and OOMs.

        self._processor = AutoProcessor.from_pretrained(settings.AI_MODEL)
        self._model = AutoModelForMultimodalLM.from_pretrained(
            settings.AI_MODEL, **load_kwargs
        )

    def _initial_messages(self, request: InsightRequest) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        for name, data_uri in (request.images or {}).items():
            content.append({"type": "text", "text": f"Evidence image: {name}"})
            content.append({"type": "image", "image": data_uri})
        content.append(
            {
                "type": "text",
                "text": evidence_prompt(
                    json.dumps(request.evidence, indent=2, default=str),
                    list((request.images or {}).keys()),
                ),
            }
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT + "\n" + TOOL_CALL_INSTRUCTIONS},
            {"role": "user", "content": content},
        ]

    def _parse(self, decoded: str) -> dict[str, Any]:
        match = re.search(r"\{.*\}", decoded, re.DOTALL)
        if not match:
            raise ValueError("model did not return a JSON object")
        payload = json.loads(match.group(0))
        if isinstance(payload, dict) and payload.get("tool_calls"):
            return {"tool_calls": payload["tool_calls"]}
        return {"content": payload}

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        request: InsightRequest | None = None,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self._load()
        assert self._model is not None and self._processor is not None

        template_kwargs: dict[str, Any] = {
            "tokenize": False,
            "add_generation_prompt": True,
            "enable_thinking": settings.AI_ENABLE_THINKING,
        }
        if tools:
            template_kwargs["tools"] = tools

        try:
            text = self._processor.apply_chat_template(messages, **template_kwargs)
        except (TypeError, ValueError):
            # Older processors do not accept a tools kwarg; fall back to the
            # text instruction in the system prompt.
            template_kwargs.pop("tools", None)
            text = self._processor.apply_chat_template(messages, **template_kwargs)

        inputs = self._processor(text=text, return_tensors="pt").to(self._model.device)
        output = self._model.generate(
            **inputs,
            max_new_tokens=settings.AI_MAX_NEW_TOKENS,
            do_sample=True,
            temperature=1.0,
            top_p=0.95,
            top_k=64,
        )
        generated = output[0][len(inputs["input_ids"][0]) :]
        decoded = self._processor.decode(generated, skip_special_tokens=True)
        return self._parse(decoded)

    def generate(self, request: InsightRequest) -> dict[str, Any]:
        result = self.chat(self._initial_messages(request))
        content = result.get("content")
        if not isinstance(content, dict):
            raise ValueError("model did not return an insight object")
        return content


def get_backend() -> InsightBackend:
    if settings.AI_BACKEND == "transformers":
        return TransformersBackend()
    return FakeBackend()
