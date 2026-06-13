"""
Llama-3-8B-Instruct LoRA fine-tuning — Phase 5 Layer B.

Fine-tunes meta-llama/Meta-Llama-3-8B-Instruct with QLoRA on
(reasoning_text → penalty_type) pairs from the incidents table.

Architecture role:
  Layer A: XGBoost on tabular features  → 7-class logit vector
  Layer B: Llama-3-8B-LoRA on text     → 7-class logit vector  ← this file
  Meta:    LR stacked ensemble (in predictor_v2.py)

Training details:
  - QLoRA: 4-bit NF4 quantisation + fp16 LoRA adapter (r=16, alpha=32)
  - Target modules: q_proj, v_proj, k_proj, o_proj
  - Format: instruction-tuned classification
  - Time: ~6 hours on Modal A100 with 800 training examples

Output:
  models/llama-lora-penalty-v1/   — HuggingFace adapter weights

Prerequisites:
  1. DATABASE_URL set with incidents table populated (≥300 rows with reasoning_text)
  2. XGBoost model trained first: python -m packages.ml.train
  3. HF_TOKEN with access to meta-llama/Meta-Llama-3-8B-Instruct

Usage (Modal A100):
    pip install modal
    modal run packages/ml/train_llama_lora.py

Usage (local, requires 80GB VRAM):
    python -m packages.ml.train_llama_lora --local
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

log = logging.getLogger("train_llama_lora")

BASE_MODEL    = "meta-llama/Meta-Llama-3-8B-Instruct"
OUTPUT_DIR    = Path("models/llama-lora-penalty-v1")
PENALTY_CLASSES = ["NFA", "REP", "5s", "10s", "DT", "GRID", "DSQ"]

LORA_R       = 16
LORA_ALPHA   = 32
LORA_DROPOUT = 0.05
TARGET_MODS  = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

EPOCHS       = 3
BATCH_SIZE   = 4
GRAD_ACCUM   = 4
LR           = 2e-4
MAX_SEQ_LEN  = 512
WARMUP_RATIO = 0.05

_SYSTEM = (
    "You are an FIA stewards' penalty classifier. "
    "Given an incident description, output exactly one penalty class from: "
    "NFA, REP, 5s, 10s, DT, GRID, DSQ. "
    "Output only the class label, nothing else."
)

# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _make_prompt(reasoning_text: str) -> str:
    return (
        f"<|begin_of_text|>"
        f"<|start_header_id|>system<|end_header_id|>\n\n"
        f"{_SYSTEM}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n\n"
        f"Incident description:\n{reasoning_text[:400]}<|eot_id|>"
        f"<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def _make_training_example(reasoning_text: str, penalty_type: str) -> str:
    return _make_prompt(reasoning_text) + penalty_type + "<|eot_id|>"


# ---------------------------------------------------------------------------
# Data loading from Postgres
# ---------------------------------------------------------------------------

def load_training_data(db_url: str) -> list[dict]:
    import psycopg2

    conn = psycopg2.connect(db_url)
    cur  = conn.cursor()
    cur.execute("""
        SELECT i.reasoning_text, i.penalty_type
        FROM incidents i
        WHERE i.reasoning_text IS NOT NULL
          AND i.reasoning_text != ''
          AND i.penalty_type IS NOT NULL
          AND i.penalty_type = ANY(%s)
        ORDER BY i.created_at DESC
    """, (PENALTY_CLASSES,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    log.info("Loaded %d training examples from DB", len(rows))
    return [{"text": _make_training_example(r[0], r[1])} for r in rows]


# ---------------------------------------------------------------------------
# Training (runs inside Modal container or locally with GPU)
# ---------------------------------------------------------------------------

def train(db_url: str, output_dir: Path = OUTPUT_DIR) -> Path:
    import os

    import torch

    try:
        import bitsandbytes  # type: ignore[import]  # noqa: F401
        from datasets import Dataset  # type: ignore[import]
        from peft import LoraConfig, TaskType, get_peft_model  # type: ignore[import]
        from transformers import (  # type: ignore[import]
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )
    except ImportError as exc:
        raise ImportError(
            "Training deps missing. Inside Modal they are pre-installed.\n"
            "Locally: pip install transformers peft bitsandbytes datasets accelerate"
        ) from exc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    hf_token = os.environ.get("HF_TOKEN")
    examples = load_training_data(db_url)

    if len(examples) < 50:
        raise ValueError(
            f"Only {len(examples)} training examples — need ≥50. "
            "Populate the incidents table first: python scripts/run_extraction.py"
        )

    log.info("Training on %d examples", len(examples))

    # QLoRA: 4-bit quantisation
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    log.info("Loading %s with 4-bit quantisation ...", BASE_MODEL)
    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL, token=hf_token, padding_side="right"
    )
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        token=hf_token,
    )
    model.config.use_cache = False

    # LoRA adapter
    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        target_modules=TARGET_MODS,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Dataset
    ds = Dataset.from_list(examples)

    def _tokenize(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=MAX_SEQ_LEN,
            padding="max_length",
        )

    ds = ds.map(_tokenize, batched=True, remove_columns=["text"])

    # Train/eval split
    split = ds.train_test_split(test_size=0.1, seed=42)

    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        warmup_ratio=WARMUP_RATIO,
        learning_rate=LR,
        fp16=True,
        logging_steps=20,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        report_to="none",
        dataloader_num_workers=0,
        optim="paged_adamw_8bit",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=split["train"],
        eval_dataset=split["test"],
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )

    log.info("Starting LoRA fine-tuning (%d epochs)...", EPOCHS)
    trainer.train()

    log.info("Saving LoRA adapter to %s ...", output_dir)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    log.info("Done. Adapter saved at %s", output_dir)
    return output_dir


# ---------------------------------------------------------------------------
# Modal deployment
# ---------------------------------------------------------------------------

def _run_on_modal(db_url: str) -> None:
    try:
        import modal
    except ImportError:
        print("modal not installed. Run: pip install modal")
        sys.exit(1)

    image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install(
            "torch>=2.2.0",
            "transformers>=4.40.0",
            "peft>=0.10.0",
            "bitsandbytes>=0.43.0",
            "datasets>=2.19.0",
            "accelerate>=0.30.0",
            "psycopg2-binary>=2.9.9",
        )
        .env({"TOKENIZERS_PARALLELISM": "false"})
    )

    app = modal.App("racejudge-train-llama-lora")
    vol = modal.Volume.from_name("racejudge-models", create_if_missing=True)

    @app.function(
        image=image,
        gpu="A100",
        timeout=28800,  # 8 hours
        secrets=[modal.Secret.from_name("racejudge-secrets")],
        volumes={"/models": vol},
    )
    def train_remote() -> str:
        import os

        output = train(os.environ["DATABASE_URL"], output_dir=Path("/models/llama-lora-penalty-v1"))
        return str(output)

    with app.run():
        result = train_remote.remote()
        print(f"Training complete. Adapter saved at: {result}")
        print("Download: modal volume get racejudge-models llama-lora-penalty-v1 ./models/")


# ---------------------------------------------------------------------------
# Inference helper (used by predictor_v2.py)
# ---------------------------------------------------------------------------

class LlamaLayerB:
    """
    Layer B inference wrapper — loads the LoRA adapter for prediction.

    Usage:
        layer_b = LlamaLayerB.load("models/llama-lora-penalty-v1")
        logits = layer_b.predict_logits("Driver forced wide at Turn 1 corner...")
        # logits: dict[penalty_class, float]
    """

    def __init__(self, model, tokenizer):
        self._model     = model
        self._tokenizer = tokenizer

    @classmethod
    def load(cls, adapter_path: str | Path) -> LlamaLayerB:
        import torch
        from peft import AutoPeftModelForCausalLM  # type: ignore[import]
        from transformers import AutoTokenizer  # type: ignore[import]

        adapter_path = Path(adapter_path)
        if not adapter_path.exists():
            raise FileNotFoundError(
                f"LoRA adapter not found: {adapter_path}\n"
                "Run python -m packages.ml.train_llama_lora first."
            )

        tokenizer = AutoTokenizer.from_pretrained(str(adapter_path))
        model = AutoPeftModelForCausalLM.from_pretrained(
            str(adapter_path),
            torch_dtype=torch.float16,
            device_map="auto",
        )
        model.eval()
        return cls(model, tokenizer)

    def predict_logits(self, reasoning_text: str) -> dict[str, float]:
        """
        Returns a dict of {penalty_class: unnormalised_logit} for each of
        the 7 penalty classes. Used by the stacked meta-learner.
        """
        import torch

        prompt = _make_prompt(reasoning_text)
        inputs = self._tokenizer(
            prompt, return_tensors="pt", truncation=True, max_length=MAX_SEQ_LEN
        ).to(self._model.device)

        # Get logits for the first generated token (the penalty class)
        with torch.no_grad():
            out = self._model(**inputs)
            next_token_logits = out.logits[0, -1, :]  # shape: vocab_size

        # Score each class by its first-token log-prob
        class_logits: dict[str, float] = {}
        for cls_name in PENALTY_CLASSES:
            token_ids = self._tokenizer.encode(cls_name, add_special_tokens=False)
            if token_ids:
                class_logits[cls_name] = float(next_token_logits[token_ids[0]])
            else:
                class_logits[cls_name] = -999.0

        return class_logits


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Fine-tune Llama-3-8B-Instruct on F1 penalty classification")
    parser.add_argument("--modal", action="store_true", help="Run on Modal A100 GPU")
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="Output directory for adapter")
    parser.add_argument("--db-url", default=None, help="DATABASE_URL override (default: read from env)")
    args = parser.parse_args()

    import os
    from pathlib import Path as _Path
    env_path = _Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set. Add to .env or pass --db-url.")
        sys.exit(1)

    if args.modal:
        _run_on_modal(db_url)
    else:
        output = train(db_url, output_dir=args.output)
        print(f"\nLoRA adapter saved at: {output}")
        print("Update predictor_v2.py: LLAMA_ADAPTER_PATH = " + repr(str(output)))


if __name__ == "__main__":
    main()
