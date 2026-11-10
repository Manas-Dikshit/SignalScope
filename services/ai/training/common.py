"""Shared helpers for the Phase 5 synthetic RF fine-tuning scaffold.

The dataset is built *offline* and *deterministically*:

1. Synthesize an I/Q recording with ``signalscope_dsp.synth``.
2. Run the same DSP stages the API worker runs (conditioning, spectral
   features, modulation classification, symbol-rate candidates, burst
   statistics, fingerprint).
3. Assemble an evidence bundle shaped exactly like the API's
   ``EvidenceBundle``.
4. Derive an ``InsightResponse`` target from that evidence, never from the
   generator's ground truth. Ground truth is kept only in ``metadata`` for
   evaluation.
5. Optionally render the same PSD/waterfall/constellation/M-th-power images the
   API sends to Gemma.

Nothing here downloads model weights or calls a network service.
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

# ── Repo-relative path setup ─────────────────────────────────────────────────
# ``services/ai`` must be importable as the package root so ``app.*`` resolves
# to the AI sidecar, and ``services/dsp-worker`` must be importable so the real
# DSP pipeline is reused instead of a copy.

TRAINING_DIR = Path(__file__).resolve().parent
AI_ROOT = TRAINING_DIR.parent
REPO_ROOT = AI_ROOT.parents[1]
DSP_ROOT = REPO_ROOT / "services" / "dsp-worker"

for _path in (AI_ROOT, DSP_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.config import settings  # noqa: E402
from app.prompts import SYSTEM_PROMPT, TOOL_CALL_INSTRUCTIONS, evidence_prompt  # noqa: E402
from app.schemas import InsightResponse  # noqa: E402
from app.validation import (  # noqa: E402
    evidence_estimate_names,
    render_template,
    validate_insight,
    validate_tool_trace,
)
from signalscope_dsp.demodulation import demod_fsk, demod_psk, demod_qam  # noqa: E402
from signalscope_dsp.detection import burst_stats, detect_bursts  # noqa: E402
from signalscope_dsp.features import extract_spectral_features  # noqa: E402
from signalscope_dsp.fec.validation import bits_to_bytes  # noqa: E402
from signalscope_dsp.fingerprint import compute_fingerprint  # noqa: E402
from signalscope_dsp.modulation import (  # noqa: E402
    classify_modulation_estimate,
    estimate_symbol_rate_candidates,
)
from signalscope_dsp.preprocessing import ConditioningConfig, condition_signal  # noqa: E402
from signalscope_dsp.synth import SynthConfig, generate_signal  # noqa: E402

# Re-exported so callers (and tests) do not need to re-implement the honesty
# rules in a second place.
__all__ = [
    "SYNTH_MODULATIONS",
    "SYNTH_TO_DSP_LABEL",
    "DEMOD_LABELS",
    "SyntheticCase",
    "LOW_CONFIDENCE_THRESHOLD",
    "TRAINING_DIR",
    "REPO_ROOT",
    "generate_cases",
    "build_evidence_bundle",
    "build_record",
    "build_target",
    "attach_images",
    "render_synthetic_images",
    "numeric_honesty_violations",
    "evidence_estimate_names",
    "render_template",
    "validate_insight",
    "validate_tool_trace",
    "write_jsonl",
    "read_jsonl",
    "SYSTEM_PROMPT",
    "TOOL_CALL_INSTRUCTIONS",
    "evidence_prompt",
]

SYNTH_MODULATIONS = ("bpsk", "qpsk", "8psk", "16qam", "64qam", "2fsk", "4fsk")

SYNTH_TO_DSP_LABEL = {
    "bpsk": "BPSK",
    "qpsk": "QPSK",
    "8psk": "8-PSK",
    "16qam": "16-QAM",
    "64qam": "64-QAM",
    "2fsk": "2-FSK",
    "4fsk": "4-FSK",
}

DEMOD_LABELS = tuple(SYNTH_TO_DSP_LABEL.values())

# Below this DSP confidence an analyst should ask a tool to discriminate the
# competing modulation hypotheses. This mirrors ``AI_MAX_TOOL_STEPS``-era
# prompts and the FakeBackend's low-confidence behaviour.
LOW_CONFIDENCE_THRESHOLD = 0.55

_PLACEHOLDER_RE = re.compile(r"\{\{estimate:[A-Za-z0-9_]+\}\}")
_DIGIT_RE = re.compile(r"\d")


# ── Case generation ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SyntheticCase:
    case_id: str
    split: str
    synth_modulation: str
    config: SynthConfig
    iq_gain_imbalance_db: float
    iq_phase_error_deg: float
    dc_offset: float

    @property
    def ground_truth_label(self) -> str:
        return SYNTH_TO_DSP_LABEL[self.synth_modulation]

    def metadata(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "case_id": self.case_id,
            "synth_modulation": self.synth_modulation,
            "ground_truth_label": self.ground_truth_label,
            "sample_rate_hz": cfg.sample_rate_hz,
            "symbol_rate_hz": cfg.symbol_rate_hz,
            "carrier_offset_hz": cfg.carrier_offset_hz,
            "snr_db": cfg.snr_db,
            "n_symbols": cfg.n_symbols,
            "burst": cfg.burst,
            "convolutional_code": cfg.apply_conv_code,
            "seed": cfg.seed,
            "impairments": {
                "iq_gain_imbalance_db": self.iq_gain_imbalance_db,
                "iq_phase_error_deg": self.iq_phase_error_deg,
                "dc_offset": self.dc_offset,
            },
        }


def _split_for(index: int, per_modulation: int) -> str:
    """Stratify every modulation across train/val/test.

    The split is deterministic and keeps at least one train example for every
    modulation, even at tiny smoke-test sizes.
    """

    if per_modulation <= 1:
        return "train"

    n_val = 1 if per_modulation >= 3 else 0
    n_test = 1 if per_modulation >= 4 else 0
    n_train = max(1, per_modulation - n_val - n_test)
    if index < n_train:
        return "train"
    if index < n_train + n_val:
        return "val"
    return "test"


def generate_cases(
    per_modulation: int = 4,
    *,
    seed: int = 20261110,
    snr_choices: Iterable[float] = (-2.0, 5.0, 15.0, 25.0),
) -> list[SyntheticCase]:
    """Create a deterministic, stratified list of synthetic cases."""

    if per_modulation < 1:
        raise ValueError("per_modulation must be >= 1")

    snrs = tuple(float(value) for value in snr_choices)
    if not snrs:
        raise ValueError("snr_choices must not be empty")

    cases: list[SyntheticCase] = []
    for mod_index, modulation in enumerate(SYNTH_MODULATIONS):
        for index in range(per_modulation):
            rng = random.Random(seed * 1009 + mod_index * 101 + index)
            symbol_rate = rng.choice([5_000.0, 10_000.0, 20_000.0, 25_000.0])
            snr_db = snrs[(mod_index + index) % len(snrs)]
            burst = (mod_index + index) % 3 == 1
            coded = (mod_index + index) % 4 == 3
            cfg = SynthConfig(
                modulation=modulation,
                sample_rate_hz=200_000.0,
                symbol_rate_hz=symbol_rate,
                carrier_offset_hz=rng.choice([-7_500.0, -2_500.0, 0.0, 2_500.0, 7_500.0]),
                snr_db=snr_db,
                n_symbols=rng.choice([1500, 2000, 2500, 3000]),
                fsk_deviation_hz=max(1_000.0, symbol_rate * 0.5),
                apply_conv_code=coded,
                burst=burst,
                burst_on_symbols=rng.choice([120, 250, 400]),
                burst_off_symbols=rng.choice([80, 160, 300]),
                seed=seed + mod_index * 10_000 + index,
            )
            case_id = f"synthetic-{modulation}-{index:03d}"
            cases.append(
                SyntheticCase(
                    case_id=case_id,
                    split=_split_for(index, per_modulation),
                    synth_modulation=modulation,
                    config=cfg,
                    iq_gain_imbalance_db=rng.choice([0.0, 0.4, 0.9]),
                    iq_phase_error_deg=rng.choice([0.0, 1.5, 4.0]),
                    dc_offset=rng.choice([0.0, 0.02, 0.05]),
                )
            )
    return cases


def apply_impairments(
    samples: np.ndarray,
    case: SyntheticCase,
) -> np.ndarray:
    """Apply small deterministic I/Q impairments on top of the synth output.

    These are intentionally *not* corrected by the conditioning stage, so the
    dataset contains imperfect captures rather than only clean simulations.
    """

    gain = 10 ** (case.iq_gain_imbalance_db / 20.0)
    phase = math.radians(case.iq_phase_error_deg)
    i = samples.real * gain
    q = samples.imag / gain
    q_corrected = q * math.cos(phase) + i * math.sin(phase)
    impaired = i + 1j * q_corrected + case.dc_offset
    return impaired.astype(np.complex64)


# ── Evidence bundle (mirrors services/api/app/tasks.py) ─────────────────────


def _estimate_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["name"]): item
        for item in evidence.get("estimates", []) or []
        if isinstance(item, dict) and item.get("name")
    }


def build_evidence_bundle(
    case: SyntheticCase,
    samples: np.ndarray,
) -> tuple[dict[str, Any], np.ndarray]:
    """Run the real DSP stages and return ``(evidence, conditioned_samples)``."""

    fs = float(case.config.sample_rate_hz)
    conditioned = condition_signal(
        samples,
        fs,
        ConditioningConfig(remove_dc_offset=True, normalize=True),
    ).samples

    features = extract_spectral_features(conditioned, fs)
    mod_est = classify_modulation_estimate(conditioned, fs)
    symbol_rates = estimate_symbol_rate_candidates(conditioned, fs)
    bursts = detect_bursts(conditioned, fs)
    b_stats = burst_stats(bursts)

    estimates = [
        features.occupied_bandwidth_hz,
        features.peak_frequency_hz,
        features.spectral_centroid_hz,
        features.spectral_flatness,
        features.crest_factor,
        features.zero_crossing_rate,
        features.snr_db,
        features.frequency_drift_rate,
        mod_est,
        *symbol_rates,
        *b_stats.values(),
    ]

    evidence: dict[str, Any] = {
        "project_id": case.case_id,
        "recording": {
            "filename": f"{case.case_id}.iq",
            "format": "synthetic-iq",
            "sample_rate_hz": fs,
            "center_frequency_hz": None,
            "duration_seconds": len(conditioned) / fs,
            "total_samples": int(len(conditioned)),
        },
        "estimates": [estimate.to_dict() for estimate in estimates],
        "available_tools": [
            "get_project_evidence",
            "run_deep_analysis",
            "try_demodulation",
            "try_fec",
            "search_similar_recordings",
        ],
        "prompt_version": settings.AI_PROMPT_VERSION,
    }

    try:
        fingerprint = compute_fingerprint(conditioned[:200_000], fs)
    except Exception as exc:  # fingerprint is a bonus, exactly as in the worker
        evidence["fingerprint"] = {"error": f"fingerprint skipped: {exc}"}
    else:
        evidence["fingerprint"] = {
            "version": fingerprint.version,
            "dimensions": fingerprint.dimensions,
            "features": fingerprint.features,
            "created_at": None,
            "evidence": fingerprint.evidence,
            "warnings": fingerprint.warnings,
        }

    return evidence, conditioned


def _primary_symbol_rate(evidence: dict[str, Any]) -> float | None:
    for item in evidence.get("estimates", []) or []:
        if item.get("name") == "symbol_rate" and item.get("value"):
            return float(item["value"])
    return None


def _samples_per_symbol(sample_rate: float, symbol_rate: float | None) -> int:
    if not symbol_rate or symbol_rate <= 0:
        return 8
    return max(2, min(64, int(round(sample_rate / symbol_rate))))


# ── Deterministic tool exemplar for low-confidence cases ────────────────────


def build_tool_exemplar(
    conditioned: np.ndarray,
    sample_rate: float,
    evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Run ``try_demodulation`` deterministically for low-confidence evidence.

    This is the only tool trace the synthetic targets use. It is produced by the
    same demodulators the private API route calls, so the trace is real evidence,
    not a hand-written example.
    """

    mod = _estimate_map(evidence).get("modulation", {})
    label = str(mod.get("value") or "")
    confidence = float(mod.get("confidence") or 0.0)

    if confidence >= LOW_CONFIDENCE_THRESHOLD or label not in DEMOD_LABELS:
        return [], None

    sps = _samples_per_symbol(sample_rate, _primary_symbol_rate(evidence))
    mode_order = {
        "BPSK": ("psk", 2),
        "QPSK": ("psk", 4),
        "8-PSK": ("psk", 8),
        "16-QAM": ("qam", 16),
        "64-QAM": ("qam", 64),
        "2-FSK": ("fsk", 2),
        "4-FSK": ("fsk", 4),
    }
    mode, order = mode_order[label]
    if mode == "qam":
        result = demod_qam(conditioned, order, sps)
    elif mode == "fsk":
        result = demod_fsk(conditioned, sample_rate, order, sps)
    else:
        result = demod_psk(conditioned, order, sps)

    soft = result.soft_bits
    mean_margin = float(np.mean(np.abs(soft))) if soft is not None and len(soft) else None
    tool_result = {
        "modulation": label,
        "samples_per_symbol": sps,
        "bits_per_symbol": result.bits_per_symbol,
        "n_symbols": int(len(result.symbols)),
        "n_bits": int(len(result.hard_bits)),
        "first_bytes_hex": bits_to_bytes(result.hard_bits)[:32].hex(),
        "mean_soft_margin": mean_margin,
        "warnings": list(result.warnings),
    }

    trace = [
        {
            "tool": "try_demodulation",
            "arguments": {"modulation": label, "samples_per_symbol": sps},
            "result": {"tool": "try_demodulation", "ok": True, "result": tool_result},
        }
    ]
    action = {
        "action": "try_demodulation",
        "args": {"modulation": label},
        "why": (
            "The DSP modulation hypothesis is low-confidence, so a direct "
            "demodulation attempt is the cheapest way to discriminate it."
        ),
        "evidence_refs": ["modulation"],
    }
    return trace, action


# ── Target construction ─────────────────────────────────────────────────────


def _confidence_phrase(confidence: float) -> str:
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return "The DSP classifier reports low confidence and competing candidates remain."
    if confidence < 0.75:
        return "The DSP classifier reports moderate confidence; treat the label as a hypothesis."
    return "The DSP classifier reports high confidence, but this remains a hypothesis rather than an identification."


def build_target(
    evidence: dict[str, Any],
    *,
    tool_trace: list[dict[str, Any]] | None = None,
    action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive a validated analyst brief from DSP evidence only.

    The generator's ground-truth label is deliberately *not* an argument here.
    A target that disagrees with the DSP pipeline is still honest, because the
    target describes the evidence the model will actually receive.
    """

    estimates = _estimate_map(evidence)
    known = evidence_estimate_names(evidence)

    mod = estimates.get("modulation", {})
    label = str(mod.get("value") or "unknown")
    confidence = float(mod.get("confidence") or 0.0)

    refs: list[str] = ["modulation"]
    sentences: list[str] = [
        "DSP evidence most strongly supports {{estimate:modulation}} as a modulation hypothesis."
    ]

    def add_value(name: str, sentence: str) -> None:
        item = estimates.get(name)
        if item and item.get("value") is not None:
            refs.append(name)
            sentences.append(sentence)

    add_value(
        "symbol_rate",
        "The leading symbol-rate candidate is {{estimate:symbol_rate}}.",
    )
    add_value(
        "occupied_bandwidth",
        "Occupied bandwidth is estimated at {{estimate:occupied_bandwidth}}.",
    )
    add_value(
        "snr_db",
        "Estimated SNR is {{estimate:snr_db}}.",
    )
    add_value(
        "spectral_flatness",
        "Spectral flatness is {{estimate:spectral_flatness}}.",
    )
    add_value(
        "crest_factor",
        "Crest factor is {{estimate:crest_factor}}.",
    )

    sentences.append(
        "This brief is an ai_hypothesis derived from deterministic DSP evidence, "
        "not a measurement or an identification."
    )

    citations = {
        name: f"Deterministic DSP estimate: {name}" for name in refs
    }

    # Close alternative hypotheses are a real conflict, not a failure.
    conflicts = []
    alternatives = mod.get("alternatives") or []
    for alt in alternatives[:2]:
        if not isinstance(alt, dict):
            continue
        alt_label = str(alt.get("value") or "")
        alt_conf = float(alt.get("confidence") or 0.0)
        if alt_label and alt_label != label and confidence - alt_conf < 0.12:
            conflicts.append(
                {
                    "between": [label, alt_label],
                    "explanation": (
                        "The classifier keeps a close alternative hypothesis. "
                        "Demodulation or FEC evidence should discriminate them."
                    ),
                    "evidence_refs": ["modulation"],
                }
            )
            break

    anomalies = []
    snr = estimates.get("snr_db", {})
    snr_value = snr.get("value")
    if isinstance(snr_value, (int, float)) and float(snr_value) < 5.0:
        anomalies.append(
            {
                "description": (
                    "The estimated SNR is low, so symbol and modulation decisions "
                    "may be unreliable."
                ),
                "severity": "medium",
                "evidence_refs": ["snr_db"],
            }
        )

    burst_duration = estimates.get("burst_duration", {})
    repetition = estimates.get("repetition_interval", {})
    if burst_duration.get("value") is not None and repetition.get("value") is not None:
        anomalies.append(
            {
                "description": (
                    "Burst structure is present. The repetition interval is an "
                    "estimate and should be confirmed with a longer capture."
                ),
                "severity": "low",
                "evidence_refs": ["burst_duration", "repetition_interval"],
            }
        )

    if label == "unknown":
        anomalies.append(
            {
                "description": "The classifier could not separate a modulation family from the evidence.",
                "severity": "medium",
                "evidence_refs": ["modulation"],
            }
        )

    actions = []
    if action is not None:
        actions.append(action)
    elif label == "unknown":
        actions.append(
            {
                "action": "run_deep_analysis",
                "args": {"fec_type": "convolutional"},
                "why": (
                    "The modulation hypothesis is unresolved; deep analysis can "
                    "re-check modulation, timing, and framing over the ROI."
                ),
                "evidence_refs": ["modulation"],
            }
        )

    unknowns = [
        "The FEC scheme and frame boundaries are not present in the evidence bundle.",
        "Transmitter identity is not determined by DSP evidence.",
    ]
    if evidence.get("recording", {}).get("center_frequency_hz") is None:
        unknowns.append("Center frequency is not declared in the recording metadata.")

    limitations = [
        "Deterministic DSP evidence only; raw IQ is never sent to the model.",
        "Modulation and symbol rate are hypotheses or estimates, not measurements.",
        "This output is an ai_hypothesis, not an identification or a guarantee.",
    ]
    if "fingerprint" in evidence:
        limitations.append(
            "Spectral similarity is evidence of similar shape, not an identification."
        )

    payload = {
        "summary_template": " ".join(sentences),
        "hypothesis": {
            "label": label,
            "agreement_with_dsp": label != "unknown",
            "confidence_note": _confidence_phrase(confidence),
            "evidence_refs": refs,
        },
        "conflicts": conflicts,
        "anomalies": anomalies,
        "recommended_actions": actions,
        "unknowns": unknowns,
        "limitations": limitations,
        "citations": citations,
        "tool_trace": tool_trace or [],
        "model_name": "",
        "prompt_version": str(evidence.get("prompt_version") or ""),
    }

    response: InsightResponse = validate_insight(
        payload,
        evidence,
        tool_trace=payload["tool_trace"],
    )
    return response.model_dump(mode="json")


# ── Numeric-honesty helper ───────────────────────────────────────────────────


def numeric_honesty_violations(payload: dict[str, Any]) -> list[str]:
    """Return prose fields that contain a digit outside a placeholder.

    Structured tool arguments (``samples_per_symbol``) and categorical
    modulation labels such as ``16-QAM`` are allowed. Everything a human reads
    as a measurement must go through ``{{estimate:name}}``.
    """

    violations: list[str] = []

    template = str(payload.get("summary_template") or "")
    stripped = _PLACEHOLDER_RE.sub("", template)
    if _DIGIT_RE.search(stripped):
        violations.append("summary_template contains a numeric value outside a placeholder")

    hypothesis = payload.get("hypothesis") or {}
    for field in ("confidence_note",):
        text = str(hypothesis.get(field) or "")
        if _DIGIT_RE.search(text):
            violations.append(f"hypothesis.{field} contains a numeric value")

    for index, conflict in enumerate(payload.get("conflicts") or []):
        if _DIGIT_RE.search(str((conflict or {}).get("explanation") or "")):
            violations.append(f"conflicts[{index}].explanation contains a numeric value")

    for index, anomaly in enumerate(payload.get("anomalies") or []):
        if _DIGIT_RE.search(str((anomaly or {}).get("description") or "")):
            violations.append(f"anomalies[{index}].description contains a numeric value")

    for index, action in enumerate(payload.get("recommended_actions") or []):
        if _DIGIT_RE.search(str((action or {}).get("why") or "")):
            violations.append(f"recommended_actions[{index}].why contains a numeric value")

    for field in ("unknowns", "limitations"):
        for index, text in enumerate(payload.get(field) or []):
            if _DIGIT_RE.search(str(text)):
                violations.append(f"{field}[{index}] contains a numeric value")

    return violations


# ── Optional image rendering ─────────────────────────────────────────────────

_EVIDENCE_IMAGES_MODULE: Any | None = None


def _load_evidence_images() -> Any:
    """Load ``services/api/app/evidence_images.py`` without the ``app`` clash.

    Both the API and AI services use an ``app`` package. Importing by file path
    under a unique module name keeps the API renderer reusable from a training
    script that already has ``services/ai`` on ``sys.path``.
    """

    global _EVIDENCE_IMAGES_MODULE
    if _EVIDENCE_IMAGES_MODULE is not None:
        return _EVIDENCE_IMAGES_MODULE

    path = REPO_ROOT / "services" / "api" / "app" / "evidence_images.py"
    if not path.exists():
        raise FileNotFoundError(f"evidence image renderer not found: {path}")

    spec = importlib.util.spec_from_file_location(
        "signalscope_api_evidence_images", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _EVIDENCE_IMAGES_MODULE = module
    return module


def attach_images(
    evidence: dict[str, Any],
    bundle: Any,
) -> None:
    evidence["evidence_images"] = bundle.audit
    evidence["image_total_bytes"] = bundle.total_bytes
    if not bundle.images:
        evidence["evidence_images_warning"] = (
            "No evidence images were rendered; see evidence_images audit."
        )


def render_synthetic_images(
    samples: np.ndarray,
    sample_rate: float,
    *,
    modulation: str | None = None,
    symbol_rate: float | None = None,
    max_image_bytes: int = 300_000,
    max_total_bytes: int = 1_000_000,
) -> Any:
    module = _load_evidence_images()
    return module.render_evidence_images(
        samples,
        sample_rate,
        modulation=modulation,
        symbol_rate=symbol_rate,
        max_image_bytes=max_image_bytes,
        max_total_bytes=max_total_bytes,
    )


# ── Record assembly ─────────────────────────────────────────────────────────


def build_record(
    case: SyntheticCase,
    *,
    render_images: bool = True,
    max_image_bytes: int = 300_000,
    max_total_bytes: int = 1_000_000,
) -> dict[str, Any]:
    """Build one JSONL-ready dataset record."""

    synth = generate_signal(case.config)
    samples = apply_impairments(synth.samples, case)
    evidence, conditioned = build_evidence_bundle(case, samples)

    tool_trace, action = build_tool_exemplar(
        conditioned,
        float(case.config.sample_rate_hz),
        evidence,
    )

    images: dict[str, str] = {}
    if render_images:
        estimates = _estimate_map(evidence)
        modulation = (estimates.get("modulation") or {}).get("value")
        symbol_rate = _primary_symbol_rate(evidence)
        bundle = render_synthetic_images(
            conditioned,
            float(case.config.sample_rate_hz),
            modulation=str(modulation) if modulation else None,
            symbol_rate=symbol_rate,
            max_image_bytes=max_image_bytes,
            max_total_bytes=max_total_bytes,
        )
        images = bundle.images
        attach_images(evidence, bundle)

    target = build_target(evidence, tool_trace=tool_trace, action=action)

    # Re-validate the serialized target, including the tool trace. This is the
    # same contract the AI sidecar enforces on model output.
    validate_insight(target, evidence, tool_trace=target.get("tool_trace") or [])
    rendered = render_template(target["summary_template"], evidence)
    if "[unknown:" in rendered:
        raise ValueError(f"{case.case_id}: target rendered an unknown placeholder")

    violations = numeric_honesty_violations(target)
    if violations:
        raise ValueError(f"{case.case_id}: numeric honesty violation(s): {violations}")

    top_mod = (_estimate_map(evidence).get("modulation") or {})
    top_label = str(top_mod.get("value") or "unknown")
    top_confidence = float(top_mod.get("confidence") or 0.0)
    expected_tool = (
        "try_demodulation"
        if tool_trace and top_label in DEMOD_LABELS
        else None
    )

    metadata = case.metadata()
    metadata.update(
        {
            "top_modulation": top_label,
            "top_modulation_confidence": top_confidence,
            "low_confidence": top_confidence < LOW_CONFIDENCE_THRESHOLD,
            "expected_tool": expected_tool,
            "has_tool_trace": bool(tool_trace),
            "has_images": bool(images),
            "image_names": sorted(images),
            "prompt_version": evidence.get("prompt_version"),
        }
    )

    return {
        "id": case.case_id,
        "split": case.split,
        "prompt": evidence_prompt(
            json.dumps(evidence, indent=2, default=str),
            sorted(images),
        ),
        "target": json.dumps(target, sort_keys=True, default=str),
        "images": images,
        "evidence": evidence,
        "metadata": metadata,
    }


# ── JSONL helpers ───────────────────────────────────────────────────────────


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, default=str))
            handle.write("\n")
            count += 1
    return count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
