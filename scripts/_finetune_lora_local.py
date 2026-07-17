"""
Local LoRA fine-tune of BGE-M3 on the F1 stewards' similarity pairs.
Runs on Apple Silicon (MPS). Temp script (uncommitted, prefixed with _).

- Train: MultipleNegativesRankingLoss on the 'similar' (anchor, positive) pairs
  (in-batch negatives — no explicit negatives needed).
- Eval gate: held-out triplet accuracy, BASE vs TUNED. Only saves the tuned
  model if it beats base; otherwise we keep base (search already works on base).
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

random.seed(42)
ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "data" / "parsed" / "decisions.jsonl"
PAIRS = ROOT / "data" / "annotations" / "similarity_pairs.jsonl"
OUT = ROOT / "data" / "models" / "bge-m3-f1"


def snippet(rec: dict, n: int = 600) -> str:
    text = rec.get("raw_text", "") or ""
    title = rec.get("title", "Untitled")
    if not text:
        return title
    low = text.lower()
    for m in ("the stewards", "having considered", "decision:", "car no", "the driver"):
        i = low.find(m)
        if i != -1:
            return text[i : i + n].strip()
    return text[:n].strip()


def load():
    idx: dict[str, str] = {}
    for line in open(DECISIONS, encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line)
            idx[r["doc_id"]] = snippet(r)
    sims: list[tuple[str, str]] = []
    dis: dict[str, list[str]] = defaultdict(list)
    allneg: set[str] = set()
    for line in open(PAIRS, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        p = json.loads(line)
        a = p["anchor_id"]
        if p.get("label") == "similar" and p.get("positive_id"):
            sims.append((a, p["positive_id"]))
        elif p.get("label") == "dissimilar" and p.get("negative_id"):
            dis[a].append(p["negative_id"])
            allneg.add(p["negative_id"])
    return idx, sims, dis, list(allneg)


idx, sims, dis, allneg = load()
sims = [(a, b) for a, b in sims if a in idx and b in idx]
random.shuffle(sims)
k = max(12, int(len(sims) * 0.15))
eval_pairs, train_pairs = sims[:k], sims[k:]


def make_neg(a: str, p: str) -> str:
    cands = [n for n in dis.get(a, []) if n in idx and n != p]
    if cands:
        return random.choice(cands)
    pool = [n for n in allneg if n in idx and n not in (a, p)]
    if pool:
        return random.choice(pool)
    keys = [kk for kk in idx if kk not in (a, p)]
    return random.choice(keys)


eval_trip = [(idx[a], idx[p], idx[make_neg(a, p)]) for a, p in eval_pairs]
train_data = [{"anchor": idx[a], "positive": idx[p]} for a, p in train_pairs]
print(f"train pairs={len(train_data)}  eval triplets={len(eval_trip)}", flush=True)

import numpy as np  # noqa: E402
from datasets import Dataset  # noqa: E402  # type: ignore[import]
from peft import LoraConfig  # noqa: E402
from sentence_transformers import (  # noqa: E402
    SentenceTransformer,
    SentenceTransformerTrainer,
    losses,
)
from sentence_transformers.training_args import (  # noqa: E402
    SentenceTransformerTrainingArguments,
)


def triplet_acc(model) -> float:
    A = [t[0] for t in eval_trip]
    P = [t[1] for t in eval_trip]
    N = [t[2] for t in eval_trip]
    ea = model.encode(A, normalize_embeddings=True, show_progress_bar=False)
    ep = model.encode(P, normalize_embeddings=True, show_progress_bar=False)
    en = model.encode(N, normalize_embeddings=True, show_progress_bar=False)
    sp = (ea * ep).sum(1)
    sn = (ea * en).sum(1)
    return float(np.mean(sp > sn))


print("loading base BGE-M3 on MPS ...", flush=True)
model = SentenceTransformer("BAAI/bge-m3", device="mps")
model.max_seq_length = 160

base_acc = triplet_acc(model)
print(f"BASE triplet accuracy: {base_acc:.4f}", flush=True)

model.add_adapter(LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05,
    target_modules=["query", "value"], bias="none",
))
print("LoRA adapter attached.", flush=True)

train_ds = Dataset.from_list(train_data)
loss = losses.MultipleNegativesRankingLoss(model)
args = SentenceTransformerTrainingArguments(
    output_dir=str(OUT / "ckpt"),
    num_train_epochs=3,
    per_device_train_batch_size=4,
    learning_rate=2e-4,
    warmup_ratio=0.1,
    fp16=False,
    bf16=False,
    logging_steps=5,
    save_strategy="no",
    report_to="none",
)
trainer = SentenceTransformerTrainer(model=model, args=args, train_dataset=train_ds, loss=loss)
trainer.train()

tuned_acc = triplet_acc(model)
print(f"\n=== RESULT ===\nBASE  triplet acc: {base_acc:.4f}\nTUNED triplet acc: {tuned_acc:.4f}", flush=True)

if tuned_acc >= base_acc + 0.01:
    try:
        model[0].auto_model = model[0].auto_model.merge_and_unload()
    except Exception as e:  # noqa: BLE001
        print("merge note:", e, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUT))
    print(f"VERDICT: TUNED WINS (+{tuned_acc - base_acc:.4f}) — saved to {OUT}", flush=True)
else:
    print("VERDICT: tuned does not beat base by >0.01 — KEEP BASE (not saving)", flush=True)
