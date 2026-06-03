"""
BGE-M3 fine-tuning — Phase 4.

Fine-tunes BAAI/bge-m3 on F1 stewards' incident similarity pairs using
triplet loss (anchor / positive / negative). Requires 300 labelled pairs
from the annotation pipeline.

Prerequisites:
  1. Run the annotation script to create 300+ labelled pairs:
       python scripts/annotate_pairs.py
  2. Export pairs to training format:
       python scripts/export_similarity_pairs.py
     This produces data/training/similarity_pairs.jsonl with schema:
       {"anchor": "...", "positive": "...", "negative": "...", "label": 1}

Usage (local, CPU/MPS):
    cd /path/to/RaceJudge && source .venv/bin/activate
    python -m packages.ml.train_embedder --pairs data/training/similarity_pairs.jsonl

Usage (Modal A10G GPU):
    pip install modal
    modal run packages/ml/train_embedder.py

Output:
    models/bge-m3-f1-v1/   — fine-tuned model (SentenceTransformer format)

After training, update EMBED_MODEL in .env:
    EMBED_MODEL=models/bge-m3-f1-v1
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger("train_embedder")

BASE_MODEL    = "BAAI/bge-m3"
OUTPUT_DIR    = Path("models/bge-m3-f1-v1")
EPOCHS        = 3
WARMUP_RATIO  = 0.1
BATCH_SIZE    = 16
LR            = 2e-5
MAX_SEQ_LEN   = 512
EVAL_SPLIT    = 0.1

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_pairs(path: str | Path) -> list[dict]:
    pairs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def build_triplets(pairs: list[dict]) -> list[dict]:
    """
    Convert similarity_pairs.jsonl to sentence-transformers triplet format.

    Input schema (from export_similarity_pairs.py):
        {"anchor": str, "positive": str, "negative": str}
      OR
        {"text_a": str, "text_b": str, "label": 0 or 1}

    If the file has text_a/text_b/label format, we need to reconstruct
    triplets by pairing each positive (label=1) with a negative (label=0)
    that shares the same anchor.
    """
    if pairs and "anchor" in pairs[0]:
        return pairs

    # text_a / text_b / label format
    positives: dict[str, list[str]] = {}
    negatives: dict[str, list[str]] = {}

    for p in pairs:
        anchor = p["text_a"]
        other  = p["text_b"]
        if p.get("label", 0) == 1:
            positives.setdefault(anchor, []).append(other)
        else:
            negatives.setdefault(anchor, []).append(other)

    triplets: list[dict] = []
    for anchor, pos_list in positives.items():
        neg_list = negatives.get(anchor, [])
        if not neg_list:
            continue
        for i, pos in enumerate(pos_list):
            neg = neg_list[i % len(neg_list)]
            triplets.append({"anchor": anchor, "positive": pos, "negative": neg})

    return triplets


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(pairs_path: str | Path, output_dir: str | Path = OUTPUT_DIR) -> Path:
    from datasets import Dataset  # type: ignore[import]
    from sentence_transformers import SentenceTransformer, SentenceTransformerTrainer, losses
    from sentence_transformers.evaluation import TripletEvaluator
    from sentence_transformers.training_args import SentenceTransformerTrainingArguments

    pairs_path  = Path(pairs_path)
    output_dir  = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("Loading pairs from %s", pairs_path)
    raw_pairs = load_pairs(pairs_path)
    triplets  = build_triplets(raw_pairs)
    log.info("Loaded %d triplets", len(triplets))

    if len(triplets) < 50:
        raise ValueError(
            f"Only {len(triplets)} triplets — need at least 50 to train. "
            "Complete more annotation pairs first."
        )

    # Train/eval split
    split_idx = max(1, int(len(triplets) * (1 - EVAL_SPLIT)))
    train_triplets = triplets[:split_idx]
    eval_triplets  = triplets[split_idx:]

    train_ds = Dataset.from_list(train_triplets)
    eval_ds  = Dataset.from_list(eval_triplets) if eval_triplets else None

    log.info("Train: %d  Eval: %d", len(train_ds), len(eval_ds) if eval_ds else 0)

    log.info("Loading base model %s ...", BASE_MODEL)
    model = SentenceTransformer(BASE_MODEL, model_kwargs={"torch_dtype": "auto"})
    model.max_seq_length = MAX_SEQ_LEN

    loss = losses.TripletLoss(model=model)

    steps_per_epoch = max(1, len(train_ds) // BATCH_SIZE)
    warmup_steps    = int(EPOCHS * steps_per_epoch * WARMUP_RATIO)

    args = SentenceTransformerTrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        warmup_steps=warmup_steps,
        learning_rate=LR,
        fp16=True,
        eval_strategy="epoch" if eval_ds else "no",
        save_strategy="epoch",
        load_best_model_at_end=bool(eval_ds),
        logging_steps=10,
        report_to="none",
    )

    evaluator = None
    if eval_ds:
        evaluator = TripletEvaluator(
            anchors   = [r["anchor"]   for r in eval_triplets],
            positives = [r["positive"] for r in eval_triplets],
            negatives = [r["negative"] for r in eval_triplets],
            name="f1-stewards-eval",
        )

    trainer = SentenceTransformerTrainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        loss=loss,
        evaluator=evaluator,
    )

    log.info("Starting fine-tuning (%d epochs, batch=%d, lr=%s) ...", EPOCHS, BATCH_SIZE, LR)
    trainer.train()

    log.info("Saving fine-tuned model to %s ...", output_dir)
    model.save_pretrained(str(output_dir))

    log.info("Fine-tuning complete. Model saved to %s", output_dir)
    log.info("Update your .env: EMBED_MODEL=%s", output_dir)
    return output_dir


# ---------------------------------------------------------------------------
# Modal deployment (optional GPU path)
# ---------------------------------------------------------------------------

def _run_on_modal(pairs_path: str) -> None:
    try:
        import modal
    except ImportError:
        print("modal not installed. Run: pip install modal")
        sys.exit(1)

    image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install(
            "sentence-transformers>=3.0.0",
            "datasets>=2.19.0",
            "torch>=2.2.0",
            "accelerate>=0.30.0",
        )
        .env({"TOKENIZERS_PARALLELISM": "false"})
    )

    app = modal.App("racejudge-train-embedder")
    vol = modal.Volume.from_name("racejudge-models", create_if_missing=True)

    @app.function(
        image=image,
        gpu="A10G",
        timeout=7200,
        volumes={"/models": vol, "/data": modal.Volume.from_name("racejudge-data", create_if_missing=True)},
    )
    def train_remote(pairs_jsonl: str) -> str:
        import tempfile
        from pathlib import Path

        pairs_path = Path(tempfile.mktemp(suffix=".jsonl"))
        pairs_path.write_text(pairs_jsonl)
        output = train(pairs_path, output_dir="/models/bge-m3-f1-v1")
        return str(output)

    pairs_data = Path(pairs_path).read_text(encoding="utf-8")
    with app.run():
        result = train_remote.remote(pairs_data)
        print(f"Training complete. Model saved at: {result}")
        print("Download from Modal volume: modal volume get racejudge-models bge-m3-f1-v1 ./models/")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Fine-tune BGE-M3 on F1 incident similarity pairs")
    parser.add_argument(
        "--pairs", default="data/training/similarity_pairs.jsonl",
        help="Path to similarity_pairs.jsonl (default: data/training/similarity_pairs.jsonl)",
    )
    parser.add_argument(
        "--output", default=str(OUTPUT_DIR),
        help=f"Output directory for fine-tuned model (default: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--modal", action="store_true",
        help="Run training on Modal A10G GPU instead of locally",
    )
    parser.add_argument("--epochs",     type=int,   default=EPOCHS,     help=f"Training epochs (default: {EPOCHS})")
    parser.add_argument("--batch-size", type=int,   default=BATCH_SIZE, help=f"Batch size (default: {BATCH_SIZE})")
    parser.add_argument("--lr",         type=float, default=LR,         help=f"Learning rate (default: {LR})")
    args = parser.parse_args()

    pairs_path = Path(args.pairs)
    if not pairs_path.exists():
        print(f"ERROR: Pairs file not found: {pairs_path}")
        print()
        print("You need to label at least 300 incident pairs first:")
        print("  python scripts/annotate_pairs.py")
        print("  python scripts/export_similarity_pairs.py")
        sys.exit(1)

    if args.modal:
        _run_on_modal(str(pairs_path))
        return

    global EPOCHS, BATCH_SIZE, LR
    EPOCHS     = args.epochs
    BATCH_SIZE = args.batch_size
    LR         = args.lr

    output = train(pairs_path, output_dir=args.output)
    print(f"\nSuccess. Add to .env:\n  EMBED_MODEL={output}")


if __name__ == "__main__":
    main()
