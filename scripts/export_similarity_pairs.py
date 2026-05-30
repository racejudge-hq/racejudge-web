"""
Export similarity_pairs.jsonl for BGE-M3 fine-tuning.

Merges labels from two sources:
  1. data/annotations/similarity_pairs.jsonl  (from annotate_pairs.py CLI)
  2. data/annotations/annotations.jsonl       (from /v1/annotations REST API)

Output: data/annotations/similarity_pairs.jsonl  (BGE-M3 triplet format)
        data/annotations/bge_m3_train.jsonl       (final fine-tune input)

BGE-M3 triplet format (per sentence-transformers TripletDataset):
  {"anchor": "<text>", "positive": "<text>", "negative": "<text>"}
  OR (binary pairs):
  {"sentence1": "<text>", "sentence2": "<text>", "label": 1.0}

Usage:
    python scripts/export_similarity_pairs.py
    python scripts/export_similarity_pairs.py --stats
    python scripts/export_similarity_pairs.py --format triplet   # default
    python scripts/export_similarity_pairs.py --format pairs     # binary pairs
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSED_JSONL     = ROOT / "data" / "parsed" / "decisions.jsonl"
CLI_PAIRS_JSONL  = ROOT / "data" / "annotations" / "similarity_pairs.jsonl"
API_ANNOTS_JSONL = ROOT / "data" / "annotations" / "annotations.jsonl"
OUTPUT_BGE       = ROOT / "data" / "annotations" / "bge_m3_train.jsonl"


# ---------------------------------------------------------------------------
# Load decision texts
# ---------------------------------------------------------------------------

def _load_decision_index() -> dict[str, dict]:
    """Return {doc_id: record} for fast lookup."""
    if not PARSED_JSONL.exists():
        sys.exit(f"[ERROR] No decisions at {PARSED_JSONL}. Run the scraper first.")
    index: dict[str, dict] = {}
    with PARSED_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                index[r["doc_id"]] = r
    return index


def _snippet(record: dict, max_chars: int = 600) -> str:
    """Return short representative text for a decision."""
    text: str = record.get("raw_text", "")
    title: str = record.get("title", "Untitled")
    if not text:
        return title
    lower = text.lower()
    for marker in ("the stewards", "having considered", "decision:", "car no", "the driver"):
        idx = lower.find(marker)
        if idx != -1:
            return text[idx: idx + max_chars].strip()
    return text[:max_chars].strip()


# ---------------------------------------------------------------------------
# Load labels from both sources
# ---------------------------------------------------------------------------

def _load_cli_pairs() -> list[dict]:
    """Load from annotate_pairs.py output format."""
    if not CLI_PAIRS_JSONL.exists():
        return []
    pairs = []
    with CLI_PAIRS_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def _load_api_annotations() -> list[dict]:
    """Load from /v1/annotations REST API format."""
    if not API_ANNOTS_JSONL.exists():
        return []
    annots = []
    with API_ANNOTS_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                annots.append(json.loads(line))
    return annots


# ---------------------------------------------------------------------------
# Merge + deduplicate
# ---------------------------------------------------------------------------

def _merge_labels(
    cli_pairs: list[dict],
    api_annots: list[dict],
) -> list[dict]:
    """
    Merge both sources into a unified list of:
      {anchor_id, positive_id, negative_id, source}

    Deduplicates by (anchor_id, positive_id/negative_id) pair.
    """
    seen: set[frozenset] = set()
    merged: list[dict] = []

    # 1. CLI pairs: each record has anchor_id, positive_id/negative_id, label
    for p in cli_pairs:
        anchor = p.get("anchor_id", "")
        other = p.get("positive_id") or p.get("negative_id") or ""
        if not anchor or not other:
            continue
        key = frozenset([anchor, other])
        if key in seen:
            continue
        seen.add(key)
        if p.get("label") == "similar":
            merged.append({"anchor_id": anchor, "positive_id": other, "negative_id": None, "source": "cli"})
        else:
            merged.append({"anchor_id": anchor, "positive_id": None, "negative_id": other, "source": "cli"})

    # 2. API annotations: each record has doc_id, positive_doc_id, negative_doc_id
    for a in api_annots:
        anchor = a.get("doc_id", "")
        pos = a.get("positive_doc_id")
        neg = a.get("negative_doc_id")
        if not anchor:
            continue
        if pos:
            key = frozenset([anchor, pos])
            if key not in seen:
                seen.add(key)
                merged.append({"anchor_id": anchor, "positive_id": pos, "negative_id": neg, "source": "api"})
        elif neg:
            key = frozenset([anchor, neg])
            if key not in seen:
                seen.add(key)
                merged.append({"anchor_id": anchor, "positive_id": None, "negative_id": neg, "source": "api"})

    return merged


# ---------------------------------------------------------------------------
# Generate BGE-M3 training examples
# ---------------------------------------------------------------------------

def _to_triplets(
    merged: list[dict],
    index: dict[str, dict],
) -> list[dict]:
    """
    Convert merged labels to BGE-M3 triplet format.

    Only records where anchor + positive exist are usable triplets.
    Records where only negative exists are skipped (no anchor/positive pair).
    """
    triplets: list[dict] = []
    skipped_missing = 0

    for row in merged:
        anchor_id = row["anchor_id"]
        pos_id = row.get("positive_id")
        neg_id = row.get("negative_id")

        if anchor_id not in index:
            skipped_missing += 1
            continue
        if pos_id and pos_id not in index:
            skipped_missing += 1
            continue
        if neg_id and neg_id not in index:
            neg_id = None  # drop missing negative; still usable as pair

        anchor_text = _snippet(index[anchor_id])

        if pos_id:
            pos_text = _snippet(index[pos_id])
            triplet: dict = {"anchor": anchor_text, "positive": pos_text}
            if neg_id:
                triplet["negative"] = _snippet(index[neg_id])
            triplets.append(triplet)

    if skipped_missing:
        print(f"  Skipped {skipped_missing} rows (doc_id not in decisions index)")

    return triplets


def _to_binary_pairs(
    merged: list[dict],
    index: dict[str, dict],
) -> list[dict]:
    """Convert to binary sentence-pair format (label=1.0 similar, 0.0 dissimilar)."""
    pairs: list[dict] = []
    for row in merged:
        anchor_id = row["anchor_id"]
        pos_id = row.get("positive_id")
        neg_id = row.get("negative_id")

        if anchor_id not in index:
            continue

        if pos_id and pos_id in index:
            pairs.append({
                "sentence1": _snippet(index[anchor_id]),
                "sentence2": _snippet(index[pos_id]),
                "label": 1.0,
            })
        if neg_id and neg_id in index:
            pairs.append({
                "sentence1": _snippet(index[anchor_id]),
                "sentence2": _snippet(index[neg_id]),
                "label": 0.0,
            })

    return pairs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Export similarity pairs for BGE-M3 fine-tuning")
    parser.add_argument("--stats", action="store_true", help="Show stats and exit without writing")
    parser.add_argument(
        "--format",
        choices=["triplet", "pairs"],
        default="triplet",
        help="Output format: triplet (anchor/pos/neg) or pairs (binary label)",
    )
    args = parser.parse_args()

    print("Loading decisions index...")
    index = _load_decision_index()
    print(f"  {len(index)} decisions loaded")

    print("Loading annotation labels...")
    cli_pairs  = _load_cli_pairs()
    api_annots = _load_api_annotations()
    print(f"  CLI pairs:       {len(cli_pairs)}")
    print(f"  API annotations: {len(api_annots)}")

    merged = _merge_labels(cli_pairs, api_annots)
    similar  = sum(1 for r in merged if r.get("positive_id"))
    dissim   = sum(1 for r in merged if r.get("negative_id") and not r.get("positive_id"))
    print(f"  Merged (deduped): {len(merged)} ({similar} positive, {dissim} negative-only)")

    if args.stats:
        # Season breakdown
        season_counts: dict[str, int] = defaultdict(int)
        for r in merged:
            aid = r["anchor_id"]
            if aid in index:
                s = str(index[aid].get("season", "?"))
                season_counts[s] += 1
        print("\nBy anchor season:")
        for s in sorted(season_counts):
            print(f"  {s}: {season_counts[s]}")
        print(f"\nTarget: 300 pairs total — {len(merged)} done ({100*len(merged)//300}%)")
        return

    if len(merged) == 0:
        print("\n[INFO] No labels yet. Run the annotation tool first:")
        print("  python scripts/annotate_pairs.py")
        print("  OR: POST to /v1/annotations with doc_id + positive_doc_id")
        return

    # Generate training examples
    if args.format == "triplet":
        examples = _to_triplets(merged, index)
        print(f"\n  Generated {len(examples)} triplet training examples")
    else:
        examples = _to_binary_pairs(merged, index)
        print(f"\n  Generated {len(examples)} binary pair training examples")

    # Write output
    OUTPUT_BGE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_BGE.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(examples)} examples to: {OUTPUT_BGE}")
    print("\nFor BGE-M3 fine-tuning, pass this file to:")
    print("  from sentence_transformers import SentenceTransformer, TripletDataset")
    print("  or use BAAI/bge-m3 with the FlagEmbedding library")


if __name__ == "__main__":
    main()
