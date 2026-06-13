"""
Incident Pair Review Tool  (Stage 2 — human adjudication)
RACEJUDGE Pre-Work — Action 2: Seed the Retriever

This is the second half of a two-stage labelling pipeline:

  Stage 1 (AI)   — an assistant reads data/parsed/decisions.jsonl, buckets every
                   decision by offence type, and proposes labelled candidate pairs
                   (with a one-line justification grounded in the stewards' own
                   reasoning) to data/annotations/candidates.jsonl.

  Stage 2 (YOU)  — this tool. It shows each candidate (both incidents + the AI's
                   proposed label + reason) and you KEEP / FLIP / DROP it. Your
                   call is final. Accepted pairs are written to
                   data/annotations/similarity_pairs.jsonl in the exact schema the
                   BGE-M3 fine-tune consumes (identical to annotate_pairs.py output,
                   so export_similarity_pairs.py reads it unchanged).

The AI removes the grunt work and the fatigue-drift; you supply the judgment that
makes the retriever sharp. Reviewing a justified candidate is far faster than
labelling from scratch, and nothing reaches the training set without your keystroke.

Candidate schema (Stage 1 output — one JSON object per line):
    {
      "anchor_id":     "<doc_id of incident A>",
      "other_id":      "<doc_id of incident B>",
      "label":         "similar" | "dissimilar",   # AI's proposal
      "reason":        "<one-line justification from the stewards' reasoning>",
      "anchor_title":  "...",   "other_title":  "...",
      "anchor_season": <int>,   "other_season": <int>,
      "offence_type":  "<bucket>"                   # optional context
    }

Usage:
    python scripts/review_pairs.py                 # guided review session (resumes)
    python scripts/review_pairs.py --validate      # check candidates.jsonl, no review
    python scripts/review_pairs.py --show-progress # show accepted-pair stats and exit
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
PARSED_JSONL = ROOT / "data" / "parsed" / "decisions.jsonl"
CANDIDATES_JSONL = ROOT / "data" / "annotations" / "candidates.jsonl"
OUTPUT_JSONL = ROOT / "data" / "annotations" / "similarity_pairs.jsonl"
DROPPED_JSONL = ROOT / "data" / "annotations" / "dropped_pairs.jsonl"

OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Target: 300 accepted pairs (per implementation plan Action 2)
# Aim for ~150 similar + 150 dissimilar for balanced training
# ---------------------------------------------------------------------------
TARGET_PAIRS = 300
TARGET_SIMILAR = 150
TARGET_DISSIMILAR = 150

REQUIRED_KEYS = ("anchor_id", "other_id", "label")

# ---------------------------------------------------------------------------
# Colours (matches annotate_pairs.py)
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  {YELLOW}[warn] {path.name} line {n}: bad JSON ({e}) — skipped{RESET}")
    return rows


def _load_decision_index() -> dict[str, dict]:
    if not PARSED_JSONL.exists():
        sys.exit(
            f"\n[ERROR] No parsed decisions at {PARSED_JSONL}\n"
            "Run the scraper first:\n"
            "  python -m packages.pipeline.scrapers.fia_scraper --season 2025\n"
        )
    index: dict[str, dict] = {}
    for r in _load_jsonl(PARSED_JSONL):
        if r.get("doc_id"):
            index[r["doc_id"]] = r
    if not index:
        sys.exit(f"\n[ERROR] {PARSED_JSONL} has no usable records.\n")
    return index


def _append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _pair_key(a_id: str, b_id: str) -> frozenset:
    return frozenset([a_id, b_id])


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _snippet(record: dict, max_chars: int = 500) -> str:
    """Short readable snippet of the incident reasoning text."""
    text: str = record.get("raw_text", "")
    title: str = record.get("title", "Untitled")
    if not text:
        return f"[No text extracted — title: {title}]"
    lower = text.lower()
    for marker in ("the stewards", "having considered", "decision:", "the drivers", "car no"):
        idx = lower.find(marker)
        if idx != -1:
            return textwrap.fill(text[idx : idx + max_chars], width=80)
    return textwrap.fill(text[:max_chars], width=80)


def _header(record: dict) -> str:
    return f"[Season {record.get('season', '?')}] {record.get('title', '')}"


def _print_candidate(
    cand: dict,
    rec_a: dict,
    rec_b: dict,
    idx: int,
    total: int,
    similar_done: int,
    dissim_done: int,
    kept: int,
    dropped: int,
) -> None:
    done = similar_done + dissim_done
    pct = int(100 * done / TARGET_PAIRS) if TARGET_PAIRS else 0
    bar_len = 40
    filled = min(bar_len, int(bar_len * done / TARGET_PAIRS)) if TARGET_PAIRS else 0
    bar = "█" * filled + "░" * (bar_len - filled)

    proposed = cand["label"]
    plabel = (f"{GREEN}SIMILAR{RESET}" if proposed == "similar"
              else f"{RED}DISSIMILAR{RESET}")

    print("\n" + "=" * 80)
    print(f"{BOLD}RACEJUDGE — Pair Review (Stage 2){RESET}   "
          f"Candidate {idx}/{total}   [{bar}] {pct}%")
    print(f"  Accepted: {GREEN}{similar_done}{RESET} sim / {RED}{dissim_done}{RESET} dis "
          f"(target {TARGET_SIMILAR}/{TARGET_DISSIMILAR})   "
          f"{DIM}kept {kept} · dropped {dropped}{RESET}")
    print("=" * 80)

    print(f"\n{CYAN}{BOLD}DOCUMENT A{RESET}")
    print(f"  {DIM}{_header(rec_a)}{RESET}\n")
    print(_snippet(rec_a))

    print(f"\n{CYAN}{BOLD}DOCUMENT B{RESET}")
    print(f"  {DIM}{_header(rec_b)}{RESET}\n")
    print(_snippet(rec_b))

    if cand.get("offence_type"):
        print(f"\n{DIM}offence type: {cand['offence_type']}{RESET}")
    print(f"\n{BOLD}AI proposes:{RESET} {plabel}")
    if cand.get("reason"):
        print(f"  {DIM}reason: {textwrap.fill(cand['reason'], width=76, subsequent_indent='          ')}{RESET}")

    print(f"\n{BOLD}Your call?{RESET}")
    print(
        f"  {GREEN}[k]{RESET} Keep (accept as {proposed})   "
        f"{YELLOW}[f]{RESET} Flip   "
        f"{RED}[x]{RESET} Drop   "
        f"{DIM}[q]{RESET} Quit & save"
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate() -> int:
    """Check candidates.jsonl against the schema + decisions index. Returns exit code."""
    index = _load_decision_index()
    cands = _load_jsonl(CANDIDATES_JSONL)
    if not cands:
        print(f"{RED}[FAIL]{RESET} No candidates found at {CANDIDATES_JSONL}")
        print("       Run Stage 1 (the AI generator) first.")
        return 1

    valid = 0
    bad_schema = 0
    bad_label = 0
    self_pairs = 0
    missing_doc = 0
    dupes = 0
    sim = 0
    dis = 0
    seen: set[frozenset] = set()

    for c in cands:
        if not all(k in c for k in REQUIRED_KEYS):
            bad_schema += 1
            continue
        if c["label"] not in ("similar", "dissimilar"):
            bad_label += 1
            continue
        a, b = c["anchor_id"], c["other_id"]
        if a == b:
            self_pairs += 1
            continue
        if a not in index or b not in index:
            missing_doc += 1
            continue
        key = _pair_key(a, b)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        valid += 1
        if c["label"] == "similar":
            sim += 1
        else:
            dis += 1

    print(f"\n{BOLD}Candidate validation — {CANDIDATES_JSONL.name}{RESET}")
    print(f"  Total lines              : {len(cands)}")
    print(f"  {GREEN}Valid, unique pairs      : {valid}{RESET}  "
          f"({sim} similar / {dis} dissimilar)")
    if bad_schema:
        print(f"  {YELLOW}Missing required keys    : {bad_schema}{RESET}")
    if bad_label:
        print(f"  {YELLOW}Bad label value          : {bad_label}{RESET}")
    if self_pairs:
        print(f"  {YELLOW}Doc paired with itself   : {self_pairs}{RESET}")
    if missing_doc:
        print(f"  {YELLOW}doc_id not in decisions  : {missing_doc}{RESET}")
    if dupes:
        print(f"  {YELLOW}Duplicate unordered pairs: {dupes}{RESET}")

    headroom = valid - TARGET_PAIRS
    print()
    if valid < TARGET_PAIRS:
        print(f"  {YELLOW}⚠ Only {valid} valid candidates — fewer than the {TARGET_PAIRS} "
              f"target. Generate ~{TARGET_PAIRS - valid + 60} more so you can drop "
              f"weak ones in review.{RESET}")
    else:
        print(f"  {GREEN}✓ {valid} valid candidates — {headroom} of headroom over the "
              f"{TARGET_PAIRS} target (room to drop weak ones).{RESET}")
    if sim < TARGET_SIMILAR or dis < TARGET_DISSIMILAR:
        print(f"  {YELLOW}⚠ Class imbalance: aim for ≥{TARGET_SIMILAR} of each so the final "
              f"set lands ~150/150 after drops.{RESET}")
    return 0


# ---------------------------------------------------------------------------
# Review loop
# ---------------------------------------------------------------------------

def review() -> None:
    index = _load_decision_index()
    cands = _load_jsonl(CANDIDATES_JSONL)
    if not cands:
        sys.exit(
            f"\n[ERROR] No candidates at {CANDIDATES_JSONL}\n"
            "Run Stage 1 (the AI generator) first, then re-run this tool.\n"
        )

    accepted = _load_jsonl(OUTPUT_JSONL)
    dropped_rows = _load_jsonl(DROPPED_JSONL)

    decided: set[frozenset] = set()
    for p in accepted:
        other = p.get("positive_id") or p.get("negative_id")
        if p.get("anchor_id") and other:
            decided.add(_pair_key(p["anchor_id"], other))
    for d in dropped_rows:
        if d.get("anchor_id") and d.get("other_id"):
            decided.add(_pair_key(d["anchor_id"], d["other_id"]))

    similar_done = sum(1 for p in accepted if p.get("label") == "similar")
    dissim_done = sum(1 for p in accepted if p.get("label") == "dissimilar")
    kept = len(accepted)
    dropped = len(dropped_rows)

    # Queue of not-yet-decided, schema-valid candidates that resolve to real docs.
    queue: list[dict] = []
    for c in cands:
        if not all(k in c for k in REQUIRED_KEYS):
            continue
        if c["label"] not in ("similar", "dissimilar"):
            continue
        a, b = c["anchor_id"], c["other_id"]
        if a == b or a not in index or b not in index:
            continue
        if _pair_key(a, b) in decided:
            continue
        queue.append(c)

    print(f"\n{BOLD}RACEJUDGE Pair Review (Stage 2 — your judgment is final){RESET}")
    print(f"Candidates file : {CANDIDATES_JSONL.name}  ({len(cands)} lines)")
    print(f"Already accepted: {similar_done} similar + {dissim_done} dissimilar = {kept}")
    print(f"To review now   : {len(queue)} undecided candidates")
    print(f"Target          : {TARGET_PAIRS} accepted ({TARGET_SIMILAR}/{TARGET_DISSIMILAR})")
    if not queue:
        print(f"\n{GREEN}Nothing left to review — every candidate is already decided.{RESET}")
        return
    print(f"\n{DIM}k = keep · f = flip · x = drop · q = quit & save{RESET}")
    print("Press Enter to start...")
    input()

    total = len(queue)
    for i, cand in enumerate(queue, 1):
        a, b = cand["anchor_id"], cand["other_id"]
        rec_a, rec_b = index[a], index[b]
        _print_candidate(cand, rec_a, rec_b, i, total,
                         similar_done, dissim_done, kept, dropped)

        final_label: str | None = None
        while True:
            choice = input("  > ").strip().lower()
            if choice in ("k", "keep", ""):
                final_label = cand["label"]
                break
            if choice in ("f", "flip"):
                final_label = "dissimilar" if cand["label"] == "similar" else "similar"
                break
            if choice in ("x", "drop", "skip"):
                final_label = None
                break
            if choice in ("q", "quit"):
                print(f"\n{GREEN}Saved and exiting. Accepted so far: {kept} "
                      f"({similar_done} sim / {dissim_done} dis){RESET}")
                return
            print(f"  {YELLOW}Enter k, f, x, or q{RESET}")

        if final_label is None:
            _append(DROPPED_JSONL, {"anchor_id": a, "other_id": b,
                                    "ai_label": cand["label"], "reason": cand.get("reason", "")})
            dropped += 1
            decided.add(_pair_key(a, b))
            print(f"  {RED}✗ Dropped{RESET}")
            continue

        record = {
            "anchor_id": a,
            "positive_id": b if final_label == "similar" else None,
            "negative_id": b if final_label == "dissimilar" else None,
            "label": final_label,
            "anchor_title": rec_a.get("title"),
            "other_title": rec_b.get("title"),
            "anchor_season": rec_a.get("season"),
            "other_season": rec_b.get("season"),
        }
        _append(OUTPUT_JSONL, record)
        decided.add(_pair_key(a, b))
        kept += 1
        if final_label == "similar":
            similar_done += 1
        else:
            dissim_done += 1
        flipped = " (flipped)" if final_label != cand["label"] else ""
        colour = GREEN if final_label == "similar" else RED
        print(f"  {colour}✓ Accepted as {final_label.upper()}{flipped}{RESET}")

        if similar_done >= TARGET_SIMILAR and dissim_done >= TARGET_DISSIMILAR:
            print(f"\n{BOLD}{GREEN}Target reached — {similar_done} similar + "
                  f"{dissim_done} dissimilar.{RESET}")
            print("Keep going to build a buffer, or press q to stop.")

    print(f"\n{BOLD}Review queue exhausted.{RESET}")
    print(f"Accepted: {similar_done} similar + {dissim_done} dissimilar = {kept}")
    print(f"Output  : {OUTPUT_JSONL}")
    if kept < TARGET_PAIRS:
        print(f"{YELLOW}Below the {TARGET_PAIRS} target — generate more candidates "
              f"(Stage 1) and re-run.{RESET}")


# ---------------------------------------------------------------------------
# Progress view
# ---------------------------------------------------------------------------

def show_progress() -> None:
    accepted = _load_jsonl(OUTPUT_JSONL)
    if not accepted:
        print("No pairs accepted yet. Run: python scripts/review_pairs.py")
        return
    similar = sum(1 for p in accepted if p.get("label") == "similar")
    dissim = sum(1 for p in accepted if p.get("label") == "dissimilar")
    total = len(accepted)
    dropped = len(_load_jsonl(DROPPED_JSONL))

    print(f"\n{BOLD}Review Progress{RESET}")
    print(f"  Accepted   : {total} / {TARGET_PAIRS}  ({100*total//TARGET_PAIRS if TARGET_PAIRS else 0}%)")
    print(f"  Similar    : {similar} / {TARGET_SIMILAR}")
    print(f"  Dissimilar : {dissim} / {TARGET_DISSIMILAR}")
    print(f"  Dropped    : {dropped}")

    seasons: dict[str, int] = {}
    for p in accepted:
        s = str(p.get("anchor_season", "?"))
        seasons[s] = seasons.get(s, 0) + 1
    print("\n  By anchor season:")
    for s, count in sorted(seasons.items()):
        print(f"    {s}: {count}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RACEJUDGE Stage-2 Pair Review Tool")
    parser.add_argument("--validate", action="store_true",
                        help="Validate candidates.jsonl against the schema and exit")
    parser.add_argument("--show-progress", action="store_true",
                        help="Show accepted-pair stats and exit")
    parser.add_argument("--candidates", metavar="PATH",
                        help="Review a different candidate file (e.g. the AI's flagged "
                             "review_queue.jsonl) instead of candidates.jsonl")
    args = parser.parse_args()

    if args.candidates:
        global CANDIDATES_JSONL
        CANDIDATES_JSONL = Path(args.candidates)

    if args.validate:
        sys.exit(validate())
    elif args.show_progress:
        show_progress()
    else:
        review()


if __name__ == "__main__":
    main()
