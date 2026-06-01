"""
Incident Pair Annotation Tool
RACEJUDGE Pre-Work — Action 2: Seed the Retriever

Loads parsed FIA decision records from data/parsed/decisions.jsonl,
presents pairs of incident descriptions, and asks you to label them
as similar or dissimilar. Labels are saved to data/annotations/similarity_pairs.jsonl.

This JSONL file is the training data for BGE-M3 fine-tuning in Phase 4.

Usage:
    python scripts/annotate_pairs.py                    # guided session
    python scripts/annotate_pairs.py --show-progress    # show stats and exit
    python scripts/annotate_pairs.py --export-stats     # print label distribution
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
PARSED_JSONL = ROOT / "data" / "parsed" / "decisions.jsonl"
OUTPUT_JSONL = ROOT / "data" / "annotations" / "similarity_pairs.jsonl"
PROGRESS_FILE = ROOT / "data" / "annotations" / "progress.json"

OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Target: 300 labelled pairs (per implementation plan Action 2)
# Aim for ~150 similar + 150 dissimilar for balanced training
# ---------------------------------------------------------------------------
TARGET_PAIRS = 300
TARGET_SIMILAR = 150
TARGET_DISSIMILAR = 150


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load_decisions() -> list[dict]:
    if not PARSED_JSONL.exists():
        sys.exit(
            f"\n[ERROR] No parsed decisions found at {PARSED_JSONL}\n"
            "Run the scraper first:\n"
            "  python -m packages.pipeline.scrapers.fia_scraper --season 2025\n"
        )
    records = []
    with PARSED_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if not records:
        sys.exit(f"\n[ERROR] {PARSED_JSONL} is empty. Run the scraper first.\n")
    return records


def _load_existing_pairs() -> list[dict]:
    if not OUTPUT_JSONL.exists():
        return []
    pairs = []
    with OUTPUT_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def _save_pair(pair: dict) -> None:
    with OUTPUT_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(pair, ensure_ascii=False) + "\n")


def _load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"annotated_pairs": [], "session_count": 0}


def _save_progress(progress: dict) -> None:
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _incident_snippet(record: dict, max_chars: int = 500) -> str:
    """Return a short readable snippet of the incident reasoning text."""
    text: str = record.get("raw_text", "")
    title: str = record.get("title", "Untitled")

    if not text:
        return f"[No text extracted — title: {title}]"

    # Try to find the 'Decision' or 'Reasoning' section
    lower = text.lower()
    for marker in ("the stewards", "having considered", "decision:", "the drivers", "car no"):
        idx = lower.find(marker)
        if idx != -1:
            snippet = text[idx : idx + max_chars]
            return textwrap.fill(snippet, width=80)

    # Fallback: first max_chars chars
    return textwrap.fill(text[:max_chars], width=80)


def _penalty_summary(record: dict) -> str:
    title = record.get("title", "")
    season = record.get("season", "?")
    return f"[Season {season}] {title}"


# ---------------------------------------------------------------------------
# Pair generation
# ---------------------------------------------------------------------------

def _already_annotated_ids(existing: list[dict]) -> set[frozenset]:
    seen: set[frozenset] = set()
    for p in existing:
        seen.add(frozenset([p["anchor_id"], p["positive_id"]]))
    return seen


def _suggest_similar_pair(
    decisions: list[dict],
    seen: set[frozenset],
) -> tuple[dict, dict] | None:
    """
    Suggest a pair likely to be similar by matching on title keywords.
    Groups documents by rough infraction type keyword.
    """
    from collections import defaultdict

    buckets: dict[str, list[dict]] = defaultdict(list)
    keywords = [
        "collision", "causing", "unsafe", "track limits", "impeding",
        "penalty", "reprimand", "blue flag", "pit lane", "start procedure",
        "weaving", "overtaking", "formation", "safety car",
    ]

    for doc in decisions:
        title_lower = doc.get("title", "").lower()
        for kw in keywords:
            if kw in title_lower:
                buckets[kw].append(doc)
                break

    # Pick a bucket with ≥2 items
    eligible = [b for b in buckets.values() if len(b) >= 2]
    if not eligible:
        return None

    random.shuffle(eligible)
    for bucket in eligible:
        docs = list(bucket)
        random.shuffle(docs)
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                pair_key = frozenset([docs[i]["doc_id"], docs[j]["doc_id"]])
                if pair_key not in seen:
                    return docs[i], docs[j]
    return None


def _suggest_dissimilar_pair(
    decisions: list[dict],
    seen: set[frozenset],
    max_tries: int = 50,
) -> tuple[dict, dict] | None:
    """Suggest two random documents (likely dissimilar)."""
    for _ in range(max_tries):
        a, b = random.sample(decisions, 2)
        pair_key = frozenset([a["doc_id"], b["doc_id"]])
        if pair_key not in seen:
            return a, b
    return None


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"

def _print_pair(a: dict, b: dict, idx: int, total: int, stats: dict) -> None:
    similar_done = stats["similar"]
    dissim_done = stats["dissimilar"]
    pct = int(100 * (similar_done + dissim_done) / TARGET_PAIRS)

    bar_len = 40
    filled = int(bar_len * (similar_done + dissim_done) / TARGET_PAIRS)
    bar = "█" * filled + "░" * (bar_len - filled)

    print("\n" + "=" * 80)
    print(f"{BOLD}RACEJUDGE — Incident Pair Annotation{RESET}   "
          f"Pair {idx}   [{bar}] {pct}%")
    print(f"  Similar: {GREEN}{similar_done}{RESET}/{TARGET_SIMILAR}   "
          f"Dissimilar: {RED}{dissim_done}{RESET}/{TARGET_DISSIMILAR}   "
          f"Total: {similar_done + dissim_done}/{TARGET_PAIRS}")
    print("=" * 80)

    print(f"\n{CYAN}{BOLD}DOCUMENT A{RESET}")
    print(f"  {DIM}{_penalty_summary(a)}{RESET}")
    print()
    print(_incident_snippet(a))

    print(f"\n{CYAN}{BOLD}DOCUMENT B{RESET}")
    print(f"  {DIM}{_penalty_summary(b)}{RESET}")
    print()
    print(_incident_snippet(b))

    print(f"\n{BOLD}Are these incidents SIMILAR in type and context?{RESET}")
    print(
        f"  {GREEN}[s]{RESET} Similar   "
        f"{RED}[d]{RESET} Dissimilar   "
        f"{YELLOW}[?]{RESET} Skip   "
        f"{DIM}[q]{RESET} Quit & save"
    )


# ---------------------------------------------------------------------------
# Main annotation loop
# ---------------------------------------------------------------------------

def annotate() -> None:
    decisions = _load_decisions()
    existing_pairs = _load_existing_pairs()
    seen_pairs = _already_annotated_ids(existing_pairs)

    similar_done = sum(1 for p in existing_pairs if p["label"] == "similar")
    dissim_done = sum(1 for p in existing_pairs if p["label"] == "dissimilar")

    print(f"\n{BOLD}RACEJUDGE Annotation Tool{RESET}")
    print(f"Loaded {len(decisions)} decisions from {PARSED_JSONL.name}")
    print(f"Already labelled: {similar_done} similar, {dissim_done} dissimilar")
    print(f"Target: {TARGET_PAIRS} pairs total ({TARGET_SIMILAR} similar + {TARGET_DISSIMILAR} dissimilar)")
    print("\nPress Enter to start...")
    input()

    pair_count = len(existing_pairs)

    while similar_done < TARGET_SIMILAR or dissim_done < TARGET_DISSIMILAR:
        # Decide whether to suggest a similar or dissimilar pair
        need_similar = similar_done < TARGET_SIMILAR
        need_dissim = dissim_done < TARGET_DISSIMILAR

        if need_similar and (not need_dissim or random.random() < 0.5):
            result = _suggest_similar_pair(decisions, seen_pairs)
        else:
            result = _suggest_dissimilar_pair(decisions, seen_pairs)

        if result is None:
            print(f"\n{YELLOW}No more unique pairs to suggest. Session complete.{RESET}")
            break

        a, b = result
        pair_count += 1

        _print_pair(a, b, pair_count, TARGET_PAIRS, {"similar": similar_done, "dissimilar": dissim_done})

        while True:
            choice = input("  > ").strip().lower()
            if choice in ("s", "similar"):
                label = "similar"
                break
            if choice in ("d", "dissimilar"):
                label = "dissimilar"
                break
            if choice in ("?", "skip", ""):
                label = "skip"
                break
            if choice in ("q", "quit"):
                print(f"\n{GREEN}Saved and exiting. Labelled so far: {similar_done + dissim_done}{RESET}")
                return
            print(f"  {YELLOW}Enter s, d, ?, or q{RESET}")

        if label is None:
            continue

        pair = {
            "anchor_id": a["doc_id"],
            "positive_id": b["doc_id"] if label == "similar" else None,
            "negative_id": b["doc_id"] if label == "dissimilar" else None,
            "label": label,
            "anchor_title": a["title"],
            "other_title": b["title"],
            "anchor_season": a.get("season"),
            "other_season": b.get("season"),
        }
        _save_pair(pair)
        seen_pairs.add(frozenset([a["doc_id"], b["doc_id"]]))

        if label == "similar":
            similar_done += 1
            print(f"  {GREEN}✓ Labelled SIMILAR{RESET}")
        else:
            dissim_done += 1
            print(f"  {RED}✓ Labelled DISSIMILAR{RESET}")

    print(f"\n{BOLD}{GREEN}Target reached!{RESET}")
    print(f"Total labelled: {similar_done} similar + {dissim_done} dissimilar = {similar_done + dissim_done} pairs")
    print(f"Output: {OUTPUT_JSONL}")


# ---------------------------------------------------------------------------
# Stats / progress view
# ---------------------------------------------------------------------------

def show_progress() -> None:
    existing = _load_existing_pairs()
    if not existing:
        print("No pairs labelled yet. Run: python scripts/annotate_pairs.py")
        return

    similar = sum(1 for p in existing if p["label"] == "similar")
    dissim = sum(1 for p in existing if p["label"] == "dissimilar")
    total = len(existing)

    print(f"\n{BOLD}Annotation Progress{RESET}")
    print(f"  Total labelled : {total} / {TARGET_PAIRS}  ({100*total//TARGET_PAIRS}%)")
    print(f"  Similar        : {similar} / {TARGET_SIMILAR}")
    print(f"  Dissimilar     : {dissim} / {TARGET_DISSIMILAR}")

    # Season breakdown
    seasons: dict[str, int] = {}
    for p in existing:
        s = str(p.get("anchor_season", "?"))
        seasons[s] = seasons.get(s, 0) + 1
    print("\n  By anchor season:")
    for s, count in sorted(seasons.items()):
        print(f"    {s}: {count} pairs")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RACEJUDGE Incident Pair Annotation Tool")
    parser.add_argument("--show-progress", action="store_true", help="Show stats and exit")
    args = parser.parse_args()

    if args.show_progress:
        show_progress()
    else:
        annotate()


if __name__ == "__main__":
    main()
