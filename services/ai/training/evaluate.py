"""Evaluate citation, placeholder, tool-choice, and numeric-honesty quality.

Two modes:

* ``--self-check`` (default): treat the exported gold targets as predictions.
  This proves the dataset itself satisfies the AI sidecar contract without a
  model. It does **not** measure fine-tuned model quality.
* ``--predictions path.jsonl``: score model outputs. Each line must contain
  ``{"id": "...", "response": {...}}`` (``payload`` is also accepted).

After a real QLoRA run, export predictions in that shape and score them here.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import (  # noqa: E402
    TRAINING_DIR,
    evidence_estimate_names,
    numeric_honesty_violations,
    read_jsonl,
    render_template,
    validate_insight,
)

_PLACEHOLDER_RE = re.compile(r"\{\{estimate:([A-Za-z0-9_]+)\}\}")


@dataclass
class SampleResult:
    record_id: str
    schema_valid: bool = False
    citation_valid: bool = False
    placeholder_valid: bool = False
    render_ok: bool = False
    numeric_honest: bool = False
    modulation_match: bool = False
    tool_choice_correct: bool = False
    tool_argument_correct: bool = False
    expected_tool: str | None = None
    predicted_tools: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class Aggregate:
    total: int = 0
    schema_valid: int = 0
    citation_valid: int = 0
    placeholder_valid: int = 0
    render_ok: int = 0
    numeric_honest: int = 0
    modulation_match: int = 0
    tool_choice_correct: int = 0
    tool_argument_correct: int = 0
    tool_expected: int = 0
    tool_predicted: int = 0
    tool_true_positive: int = 0
    tool_false_positive: int = 0
    tool_false_negative: int = 0

    def add(self, result: SampleResult) -> None:
        self.total += 1
        self.schema_valid += int(result.schema_valid)
        self.citation_valid += int(result.citation_valid)
        self.placeholder_valid += int(result.placeholder_valid)
        self.render_ok += int(result.render_ok)
        self.numeric_honest += int(result.numeric_honest)
        self.modulation_match += int(result.modulation_match)
        self.tool_choice_correct += int(result.tool_choice_correct)
        self.tool_argument_correct += int(result.tool_argument_correct)

        expected = result.expected_tool is not None
        predicted = bool(result.predicted_tools)
        self.tool_expected += int(expected)
        self.tool_predicted += int(predicted)
        if expected and predicted:
            self.tool_true_positive += 1
        elif predicted and not expected:
            self.tool_false_positive += 1
        elif expected and not predicted:
            self.tool_false_negative += 1

    def rate(self, value: int) -> float:
        return round(value / self.total, 4) if self.total else 0.0

    def tool_precision(self) -> float:
        denom = self.tool_true_positive + self.tool_false_positive
        return round(self.tool_true_positive / denom, 4) if denom else 0.0

    def tool_recall(self) -> float:
        denom = self.tool_true_positive + self.tool_false_negative
        return round(self.tool_true_positive / denom, 4) if denom else 0.0

    def tool_f1(self) -> float:
        precision = self.tool_precision()
        recall = self.tool_recall()
        return round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "schema_validity": self.rate(self.schema_valid),
            "citation_validity": self.rate(self.citation_valid),
            "placeholder_validity": self.rate(self.placeholder_valid),
            "render_ok": self.rate(self.render_ok),
            "numeric_honesty": self.rate(self.numeric_honest),
            "modulation_match_vs_synth_truth": self.rate(self.modulation_match),
            "tool_choice_accuracy": self.rate(self.tool_choice_correct),
            "tool_argument_accuracy": self.rate(self.tool_argument_correct),
            "tool_precision": self.tool_precision(),
            "tool_recall": self.tool_recall(),
            "tool_f1": self.tool_f1(),
            "tool_expected": self.tool_expected,
            "tool_predicted": self.tool_predicted,
            "tool_true_positive": self.tool_true_positive,
            "tool_false_positive": self.tool_false_positive,
            "tool_false_negative": self.tool_false_negative,
        }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score InsightResponse outputs for validity, honesty, and tool choice."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=TRAINING_DIR / "data",
        help="Directory containing the JSONL splits",
    )
    parser.add_argument(
        "--split",
        choices=("train", "val", "test"),
        default="test",
        help="Split to score (default: test)",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help="JSONL predictions with id + response/payload. Omit for gold self-check.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write a JSON report (default: services/ai/training/reports/eval_<split>.json)",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=0,
        help="Optional cap for quick checks",
    )
    return parser.parse_args(argv)


def _load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    predictions: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        record_id = str(item.get("id") or "")
        payload = item.get("response", item.get("payload", item))
        if not record_id or not isinstance(payload, dict):
            raise ValueError(
                "each prediction line needs an id and a response/payload object"
            )
        predictions[record_id] = payload
    return predictions


def _score(record: dict[str, Any], payload: dict[str, Any]) -> SampleResult:
    evidence = record.get("evidence") or {}
    metadata = record.get("metadata") or {}
    known = evidence_estimate_names(evidence)
    result = SampleResult(record_id=str(record.get("id") or "unknown"))

    try:
        validate_insight(payload, evidence, tool_trace=payload.get("tool_trace") or [])
        result.schema_valid = True
    except Exception as exc:  # noqa: BLE001 - report, do not crash the run
        result.issues.append(f"schema/validation: {exc}")

    citations = payload.get("citations") or {}
    result.citation_valid = bool(citations) and all(
        str(ref) in known for ref in citations
    )
    if not result.citation_valid:
        result.issues.append("citations are empty or reference unknown evidence")

    template = str(payload.get("summary_template") or "")
    placeholders = set(_PLACEHOLDER_RE.findall(template))
    result.placeholder_valid = bool(placeholders) and placeholders.issubset(known)
    if not result.placeholder_valid:
        result.issues.append("summary_template has missing or unknown placeholders")

    try:
        rendered = render_template(template, evidence)
    except Exception as exc:  # noqa: BLE001
        rendered = ""
        result.issues.append(f"render failed: {exc}")
    result.render_ok = bool(rendered) and "[unknown:" not in rendered
    if not result.render_ok:
        result.issues.append("rendered summary contains [unknown:...]")

    violations = numeric_honesty_violations(payload)
    result.numeric_honest = not violations
    if violations:
        result.issues.extend(violations)

    hypothesis = payload.get("hypothesis") or {}
    result.modulation_match = (
        str(hypothesis.get("label") or "") == str(metadata.get("ground_truth_label") or "")
    )

    result.expected_tool = metadata.get("expected_tool")
    trace = payload.get("tool_trace") or []
    result.predicted_tools = [
        str(entry.get("tool"))
        for entry in trace
        if isinstance(entry, dict) and entry.get("tool")
    ]

    expected = result.expected_tool
    result.tool_choice_correct = (
        (expected is None and not result.predicted_tools)
        or (expected is not None and expected in result.predicted_tools)
    )
    if not result.tool_choice_correct:
        result.issues.append(
            f"tool choice mismatch: expected={expected or '-'} "
            f"predicted={result.predicted_tools or '-'}"
        )

    result.tool_argument_correct = True
    if expected is not None:
        matching = [
            entry
            for entry in trace
            if isinstance(entry, dict) and entry.get("tool") == "try_demodulation"
        ]
        arg_label = (
            str((matching[0].get("arguments") or {}).get("modulation"))
            if matching
            else ""
        )
        result.tool_argument_correct = arg_label == str(
            metadata.get("top_modulation") or expected
        )
        if not result.tool_argument_correct:
            result.issues.append(
                f"tool argument mismatch: got={arg_label or '-'} "
                f"expected={metadata.get('top_modulation') or expected}"
            )

    return result


def _print_summary(aggregate: Aggregate, mode: str) -> None:
    print(f"SignalScope Phase 5 evaluation — mode: {mode}")
    print("=" * 72)
    metrics = aggregate.to_dict()
    labels = [
        ("schema_validity", "schema validity"),
        ("citation_validity", "citation validity"),
        ("placeholder_validity", "placeholder validity"),
        ("render_ok", "render without [unknown:...]"),
        ("numeric_honesty", "numeric honesty"),
        ("tool_choice_accuracy", "tool-choice accuracy"),
        ("tool_argument_accuracy", "tool-argument accuracy"),
        ("modulation_match_vs_synth_truth", "modulation match vs synth truth*"),
    ]
    for key, label in labels:
        print(f"{label:<36} {metrics[key]:>8.2%}")
    print(
        f"{'tool precision / recall / F1':<36} "
        f"{metrics['tool_precision']:.2%} / {metrics['tool_recall']:.2%} / "
        f"{metrics['tool_f1']:.2%}"
    )
    print(f"{'examples':<36} {aggregate.total:>8d}")
    print("-" * 72)
    print("* modulation match is a data-quality signal, not an honesty check:")
    print("  a target may honestly follow the DSP hypothesis even when it differs")
    print("  from the generator's ground truth.")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    data_path = args.data_dir / f"{args.split}.jsonl"
    if not data_path.exists():
        print(
            f"{data_path} not found. Run: python services/ai/training/build_dataset.py",
            file=sys.stderr,
        )
        return 2

    records = read_jsonl(data_path)
    if args.max_examples:
        records = records[: args.max_examples]
    if not records:
        print(f"{data_path} is empty.", file=sys.stderr)
        return 2

    predictions = _load_predictions(args.predictions) if args.predictions else None
    mode = "predictions" if predictions is not None else "gold-target-self-check"

    aggregate = Aggregate()
    samples: list[SampleResult] = []
    for record in records:
        record_id = str(record.get("id") or "")
        if predictions is None:
            payload = json.loads(record["target"])
        else:
            payload = predictions.get(record_id)
            if payload is None:
                result = SampleResult(
                    record_id=record_id,
                    issues=["no prediction for this id"],
                )
                aggregate.add(result)
                samples.append(result)
                continue
        result = _score(record, payload)
        aggregate.add(result)
        samples.append(result)

    _print_summary(aggregate, mode)

    report = {
        "mode": mode,
        "split": args.split,
        "data": str(data_path),
        "predictions": str(args.predictions) if args.predictions else None,
        "aggregate": aggregate.to_dict(),
        "failures": [
            {"id": sample.record_id, "issues": sample.issues}
            for sample in samples
            if sample.issues
        ],
    }

    report_path = args.report or (
        TRAINING_DIR / "reports" / f"eval_{args.split}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"report: {report_path}")

    hard_failures = aggregate.total - aggregate.schema_valid
    hard_failures += aggregate.total - aggregate.citation_valid
    hard_failures += aggregate.total - aggregate.placeholder_valid
    hard_failures += aggregate.total - aggregate.numeric_honest
    if hard_failures:
        print(f"FAIL: {hard_failures} hard contract failure(s).", file=sys.stderr)
        return 1
    print("PASS: schema, citations, placeholders, and numeric honesty all hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
