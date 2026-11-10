"""Generate the Phase 5 synthetic RF fine-tuning dataset.

This script is offline and deterministic. It runs the real DSP pipeline over
synthetic recordings, exports API-shaped evidence bundles, derives validated
``InsightResponse`` targets from that evidence, and (optionally) renders the
same evidence images the API sends to Gemma.

It never downloads weights and never trains a model.

Usage (from the repo root):

    python services/ai/training/build_dataset.py --per-modulation 4
    python services/ai/training/build_dataset.py --per-modulation 1 --no-images

Outputs:

    services/ai/training/data/train.jsonl
    services/ai/training/data/val.jsonl
    services/ai/training/data/test.jsonl
    services/ai/training/data/dataset_card.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

# ``common`` adds the AI and DSP roots to sys.path before importing app.*.
from common import (  # noqa: E402
    LOW_CONFIDENCE_THRESHOLD,
    REPO_ROOT,
    TRAINING_DIR,
    build_record,
    generate_cases,
    write_jsonl,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic synthetic RF evidence dataset (no model download)."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=TRAINING_DIR / "data",
        help="Output directory (default: services/ai/training/data)",
    )
    parser.add_argument(
        "--per-modulation",
        type=int,
        default=4,
        help="Cases per modulation (default: 4, i.e. 28 records)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20261110,
        help="Deterministic generator seed",
    )
    parser.add_argument(
        "--snr",
        nargs="+",
        type=float,
        default=[-2.0, 5.0, 15.0, 25.0],
        help="SNR values in dB, cycled across cases",
    )
    parser.add_argument(
        "--images",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Render PSD/waterfall/constellation/M-th-power images (default: on)",
    )
    parser.add_argument(
        "--max-image-bytes",
        type=int,
        default=300_000,
        help="Per-image cap, matching AI_MAX_IMAGE_BYTES",
    )
    parser.add_argument(
        "--max-total-image-bytes",
        type=int,
        default=1_000_000,
        help="Bundle cap, matching AI_MAX_TOTAL_IMAGE_BYTES",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional cap on generated cases for a quick smoke test",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    started = time.time()

    cases = generate_cases(
        per_modulation=args.per_modulation,
        seed=args.seed,
        snr_choices=args.snr,
    )
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("No cases generated.", file=sys.stderr)
        return 2

    print(
        f"Generating {len(cases)} synthetic cases "
        f"({args.per_modulation} per modulation, images={args.images}) ..."
    )

    records: list[dict] = []
    for index, case in enumerate(cases, start=1):
        try:
            record = build_record(
                case,
                render_images=args.images,
                max_image_bytes=args.max_image_bytes,
                max_total_bytes=args.max_total_image_bytes,
            )
        except Exception as exc:
            print(f"[{index}/{len(cases)}] FAILED {case.case_id}: {exc}", file=sys.stderr)
            raise
        records.append(record)
        image_count = len(record.get("images") or {})
        print(
            f"[{index}/{len(cases)}] {case.case_id} "
            f"split={case.split} mod={record['metadata']['top_modulation']} "
            f"conf={record['metadata']['top_modulation_confidence']:.2f} "
            f"images={image_count} tool={record['metadata']['expected_tool'] or '-'}"
        )

    by_split: dict[str, list[dict]] = {"train": [], "val": [], "test": []}
    for record in records:
        by_split.setdefault(record["split"], []).append(record)

    args.out.mkdir(parents=True, exist_ok=True)
    counts = {
        split: write_jsonl(args.out / f"{split}.jsonl", split_records)
        for split, split_records in by_split.items()
    }

    card = {
        "name": "signalscope-synthetic-rf-insight",
        "version": "phase5-scaffold",
        "created_unix": int(time.time()),
        "generator_seed": args.seed,
        "per_modulation": args.per_modulation,
        "snr_choices_db": list(args.snr),
        "modulations": sorted({case.synth_modulation for case in cases}),
        "ground_truth_labels": sorted({case.ground_truth_label for case in cases}),
        "images_rendered": bool(args.images),
        "counts": {split: len(items) for split, items in by_split.items()},
        "total": len(records),
        "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
        "target_contract": {
            "schema": "services/ai/app/schemas.py:InsightResponse",
            "validation": "services/ai/app/validation.py:validate_insight",
            "numeric_rule": "no digits in prose outside {{estimate:name}} placeholders",
            "tool_trace": "deterministic try_demodulation only, low-confidence cases",
        },
        "split_counts_by_modulation": {
            f"{split}:{modulation}": count
            for (split, modulation), count in Counter(
                (record["split"], record["metadata"]["synth_modulation"])
                for record in records
            ).items()
        },
        "notes": [
            "Ground truth is stored in metadata for evaluation only and is never in the prompt.",
            "Targets are derived from DSP evidence, so a target may honestly disagree with the synth label.",
            "No model weights were downloaded and no training was run.",
        ],
    }
    card_path = args.out / "dataset_card.json"
    card_path.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    elapsed = time.time() - started
    print("\nWrote:")
    for split in ("train", "val", "test"):
        print(f"  {args.out / f'{split}.jsonl'}  ({counts.get(split, 0)} records)")
    print(f"  {card_path}")
    print(f"Total {len(records)} records in {elapsed:.1f}s. No model weights were downloaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
