"""QLoRA fine-tuning scaffold for Gemma 4 E4B on SignalScope evidence bundles.

Safety posture
--------------
* The default mode is ``--plan``: it validates the dataset and prints the
  training plan. It does **not** import torch/transformers/peft, download
  weights, or start a run.
* ``--execute`` is required to actually train. It still does not auto-download
  anything unless the normal Hugging Face cache behaviour is allowed.
* ``--offline`` sets the Hugging Face offline flags and requires
  ``--local-model-path``.

Hardware expectation (4-bit QLoRA, batch 1, gradient checkpointing):
    >= 16 GB VRAM is the practical floor for E4B; 24 GB is comfortable.
    CPU training is possible in theory but not a supported path here.

The dataset's optional PNG evidence images are exported but are **not** fed to
this text-only scaffold. A processor-aware multimodal collator is intentionally
left as an explicit extension point; silently dropping images would make the
training misleading.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from common import (  # noqa: E402
    SYSTEM_PROMPT,
    TOOL_CALL_INSTRUCTIONS,
    TRAINING_DIR,
    read_jsonl,
)

CONFIG_DIR = TRAINING_DIR / "configs"
DEFAULT_CONFIG = CONFIG_DIR / "qlora_gemma4_e4b.json"


def _default_config() -> dict[str, Any]:
    return {
        "model_id": "google/gemma-4-E4B-it",
        "quantization": {
            "load_in_4bit": True,
            "bnb_4bit_quant_type": "nf4",
            "bnb_4bit_compute_dtype": "bfloat16",
            "bnb_4bit_use_double_quant": True,
        },
        "lora": {
            "r": 16,
            "alpha": 32,
            "dropout": 0.05,
            "target_modules": [
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
        },
        "training": {
            "epochs": 3,
            "batch_size": 1,
            "grad_accum": 8,
            "learning_rate": 0.0002,
            "max_seq_len": 4096,
            "bf16": True,
            "gradient_checkpointing": True,
            "logging_steps": 10,
            "save_total_limit": 2,
        },
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path | None) -> dict[str, Any]:
    config = _default_config()
    if path is not None and path.exists():
        config = _deep_merge(config, json.loads(path.read_text(encoding="utf-8")))
    return config


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QLoRA scaffold for Gemma 4 E4B (plan by default; no weights downloaded)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="JSON training config (default: services/ai/training/configs/qlora_gemma4_e4b.json)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=TRAINING_DIR / "data",
        help="Directory containing train.jsonl / val.jsonl / test.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=TRAINING_DIR / "adapters" / "gemma4-e4b-qlora",
        help="Adapter output directory",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Override the model id from the config",
    )
    parser.add_argument(
        "--local-model-path",
        type=Path,
        default=None,
        help="Local model directory (required with --offline)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually load the model and train. Default is a dry plan.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Set HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE and require a local model path.",
    )
    parser.add_argument(
        "--include-images",
        action="store_true",
        help="Reserved for a processor-aware multimodal collator (not implemented).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Override training steps for a smoke run (0 keeps the configured epochs).",
    )
    parser.add_argument(
        "--split",
        choices=("train", "val"),
        default="train",
        help="Which split to report in the plan (training always uses train + val).",
    )
    return parser.parse_args(argv)


def _load_split(data_dir: Path, split: str) -> list[dict[str, Any]]:
    path = data_dir / f"{split}.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run: python services/ai/training/build_dataset.py"
        )
    return read_jsonl(path)


def _stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    images = sum(1 for record in records if record.get("images"))
    tool = sum(
        1
        for record in records
        if (record.get("metadata") or {}).get("expected_tool") == "try_demodulation"
    )
    low_conf = sum(
        1 for record in records if (record.get("metadata") or {}).get("low_confidence")
    )
    return {
        "records": len(records),
        "with_images": images,
        "low_confidence": low_conf,
        "with_tool_trace": tool,
    }


def _plan(args: argparse.Namespace, config: dict[str, Any]) -> int:
    train = _load_split(args.data_dir, "train")
    try:
        val = _load_split(args.data_dir, "val")
    except FileNotFoundError:
        val = []
    try:
        test = _load_split(args.data_dir, "test")
    except FileNotFoundError:
        test = []

    if not train:
        print("train.jsonl is empty; build the dataset first.", file=sys.stderr)
        return 2

    training = config["training"]
    quantization = config["quantization"]
    lora = config["lora"]
    model_id = args.model_id or config["model_id"]

    print("SignalScope Phase 5 — QLoRA plan (no weights downloaded, no training run)")
    print("=" * 72)
    print(f"model:                 {model_id}")
    print(f"quantization:          {'4-bit ' + quantization['bnb_4bit_quant_type'] if quantization.get('load_in_4bit') else 'none'}")
    print(f"LoRA r/alpha/dropout:  {lora['r']}/{lora['alpha']}/{lora['dropout']}")
    print(f"LoRA target modules:   {', '.join(lora['target_modules'])}")
    print(
        "training:              "
        f"epochs={training['epochs']} batch={training['batch_size']} "
        f"grad_accum={training['grad_accum']} lr={training['learning_rate']} "
        f"max_seq_len={training['max_seq_len']}"
    )
    print(f"data dir:              {args.data_dir}")
    print(f"output dir:            {args.output_dir}")
    print("splits:")
    for name, records in (("train", train), ("val", val), ("test", test)):
        stats = _stats(records)
        print(
            f"  {name:<5} records={stats['records']:<4} "
            f"images={stats['with_images']:<4} low_conf={stats['low_confidence']:<4} "
            f"tool_trace={stats['with_tool_trace']}"
        )
    print("-" * 72)
    print("hardware: 4-bit E4B QLoRA with batch 1 + gradient checkpointing needs")
    print("          roughly >=16 GB VRAM (24 GB comfortable); CPU is not supported.")
    if any(record.get("images") for record in train):
        print("images:   exported in the dataset but intentionally NOT used by this")
        print("          text-only scaffold; wire a processor-aware collator first.")
    print(
        "guardrail: this was a plan only. Pass --execute to load the model and train."
    )
    return 0


def _execute(args: argparse.Namespace, config: dict[str, Any]) -> int:
    if args.include_images:
        raise SystemExit(
            "--include-images is not implemented. The dataset contains PNG data "
            "URIs, but a Gemma 4 processor-aware collator must be wired before "
            "images can be trained on. Dropping them silently would be misleading."
        )
    if args.offline and args.local_model_path is None:
        raise SystemExit("--offline requires --local-model-path")

    if args.offline:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    try:
        import torch
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            Trainer,
            TrainingArguments,
        )
    except ImportError as exc:
        raise SystemExit(
            "Training dependencies are missing. Install them on a GPU host with:\n"
            "  python -m pip install -r services/ai/requirements.txt "
            "-r services/ai/training/requirements-training.txt\n"
            f"Import error: {exc}"
        ) from exc

    train_records = _load_split(args.data_dir, "train")
    try:
        val_records = _load_split(args.data_dir, "val")
    except FileNotFoundError:
        val_records = []
    if not train_records:
        raise SystemExit("train.jsonl is empty; build the dataset first.")

    model_path = str(args.local_model_path) if args.local_model_path else (
        args.model_id or config["model_id"]
    )
    quantization = config["quantization"]
    lora_cfg = config["lora"]
    training = config["training"]
    max_seq_len = int(training["max_seq_len"])

    print("WARNING: --execute loads model weights and runs training. Do not run in CI.")
    print(f"Loading tokenizer/model: {model_path}")

    tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    compute_dtype = getattr(torch, str(quantization.get("bnb_4bit_compute_dtype", "bfloat16")))
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=bool(quantization.get("load_in_4bit", True)),
        bnb_4bit_quant_type=str(quantization.get("bnb_4bit_quant_type", "nf4")),
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=bool(
            quantization.get("bnb_4bit_use_double_quant", True)
        ),
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=bnb_config,
        device_map="auto",
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=bool(training["gradient_checkpointing"]),
    )
    model = get_peft_model(
        model,
        LoraConfig(
            r=int(lora_cfg["r"]),
            lora_alpha=int(lora_cfg["alpha"]),
            lora_dropout=float(lora_cfg["dropout"]),
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=list(lora_cfg["target_modules"]),
        ),
    )
    model.print_trainable_parameters()

    class EvidenceDataset(torch.utils.data.Dataset):
        def __init__(self, records: list[dict[str, Any]]) -> None:
            self.records = records

        def __len__(self) -> int:
            return len(self.records)

        def __getitem__(self, index: int) -> dict[str, Any]:
            record = self.records[index]
            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT + "\n" + TOOL_CALL_INSTRUCTIONS,
                },
                {"role": "user", "content": record["prompt"]},
            ]
            if hasattr(tokenizer, "apply_chat_template"):
                prompt_text = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            else:  # pragma: no cover - depends on the tokenizer version
                prompt_text = (
                    f"<start_of_turn>user\n{messages[0]['content']}\n\n"
                    f"{messages[1]['content']}<end_of_turn>\n<start_of_turn>model\n"
                )

            target_text = record["target"] + (tokenizer.eos_token or "")
            prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
            target_ids = tokenizer(target_text, add_special_tokens=False)["input_ids"]

            # Keep the completion intact; truncate the prompt from the left.
            if len(target_ids) >= max_seq_len:
                target_ids = target_ids[:max_seq_len]
                prompt_ids = []
            else:
                prompt_ids = prompt_ids[-(max_seq_len - len(target_ids)):]

            input_ids = prompt_ids + target_ids
            labels = [-100] * len(prompt_ids) + list(target_ids)
            return {
                "input_ids": torch.tensor(input_ids, dtype=torch.long),
                "attention_mask": torch.ones(len(input_ids), dtype=torch.long),
                "labels": torch.tensor(labels, dtype=torch.long),
            }

    class CausalLMCollator:
        def __init__(self, pad_token_id: int) -> None:
            self.pad_token_id = pad_token_id

        def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
            max_len = max(int(feature["input_ids"].shape[0]) for feature in features)
            batch = {"input_ids": [], "attention_mask": [], "labels": []}
            for feature in features:
                pad = max_len - int(feature["input_ids"].shape[0])
                batch["input_ids"].append(
                    torch.cat(
                        [
                            feature["input_ids"],
                            torch.full((pad,), self.pad_token_id, dtype=torch.long),
                        ]
                    )
                )
                batch["attention_mask"].append(
                    torch.cat(
                        [
                            feature["attention_mask"],
                            torch.zeros(pad, dtype=torch.long),
                        ]
                    )
                )
                batch["labels"].append(
                    torch.cat(
                        [
                            feature["labels"],
                            torch.full((pad,), -100, dtype=torch.long),
                        ]
                    )
                )
            return {key: torch.stack(values) for key, values in batch.items()}

    train_dataset = EvidenceDataset(train_records)
    eval_dataset = EvidenceDataset(val_records) if val_records else None

    args_kwargs: dict[str, Any] = {
        "output_dir": str(args.output_dir),
        "per_device_train_batch_size": int(training["batch_size"]),
        "gradient_accumulation_steps": int(training["grad_accum"]),
        "learning_rate": float(training["learning_rate"]),
        "num_train_epochs": float(training["epochs"]),
        "logging_steps": int(training["logging_steps"]),
        "save_strategy": "epoch",
        "save_total_limit": int(training["save_total_limit"]),
        "bf16": bool(training["bf16"]),
        "gradient_checkpointing": bool(training["gradient_checkpointing"]),
        "optim": "paged_adamw_8bit",
        "report_to": [],
        "remove_unused_columns": False,
        "dataloader_pin_memory": False,
    }
    if args.max_steps:
        args_kwargs["max_steps"] = int(args.max_steps)
    if eval_dataset is not None:
        # transformers renamed this around v4.46; support both spellings.
        try:
            training_args = TrainingArguments(eval_strategy="epoch", **args_kwargs)
        except TypeError:  # pragma: no cover - older transformers
            training_args = TrainingArguments(
                evaluation_strategy="epoch", **args_kwargs
            )
    else:
        training_args = TrainingArguments(**args_kwargs)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=CausalLMCollator(int(tokenizer.pad_token_id)),
    )

    print("Starting QLoRA training ...")
    trainer.train()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    print(f"Adapter saved to {args.output_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    config = load_config(args.config)
    if args.execute:
        return _execute(args, config)
    return _plan(args, config)


if __name__ == "__main__":
    raise SystemExit(main())
