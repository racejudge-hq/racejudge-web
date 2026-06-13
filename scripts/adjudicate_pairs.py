"""
Stage 2a — AI adjudication harness (hybrid review).

The Stage 1 candidates (candidates.jsonl) were proposed by a deterministic
regex/penalty heuristic. This harness lets a strong model (the agent driving it)
genuinely READ both full decision texts per pair and record a verdict, instead of
trusting the heuristic. It is the engine behind the "AI adjudicates all, human
reviews only the flagged subset" workflow.

Flow:
  1.  --print --start S --count N   : dump pairs [S, S+N) with both decisions'
                                       penalty + fact + body for the agent to read.
  2.  (agent reasons, writes verdicts to a JSON file)
  3.  --ingest verdicts.json        : record verdicts into adjudicated.jsonl.
      verdicts.json schema:
        [ {"i": <global pair index>, "v": "similar"|"dissimilar"|"drop",
           "c": "high"|"med"|"low", "r": "<one-line reason>"} , ... ]
  4.  --status                      : how many adjudicated / remaining.
  5.  --finalize                    : split into
        similarity_pairs.jsonl  (high-confidence agreements — locked training data)
        review_queue.jsonl      (flips + low-confidence + drops — for human Stage 2b)

The human then runs:  python scripts/review_pairs.py --candidates \
    data/annotations/review_queue.jsonl
which appends their calls to similarity_pairs.jsonl (disjoint, so no conflict).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSED_JSONL = ROOT / "data" / "parsed" / "decisions.jsonl"
CANDIDATES_JSONL = ROOT / "data" / "annotations" / "candidates.jsonl"
ADJUDICATED_JSONL = ROOT / "data" / "annotations" / "adjudicated.jsonl"
OUTPUT_JSONL = ROOT / "data" / "annotations" / "similarity_pairs.jsonl"
REVIEW_QUEUE_JSONL = ROOT / "data" / "annotations" / "review_queue.jsonl"

BODY_CHARS = 1300


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.open(encoding="utf-8"):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _index() -> dict[str, dict]:
    idx = {}
    for r in _load_jsonl(PARSED_JSONL):
        if r.get("doc_id"):
            idx[r["doc_id"]] = r
    return idx


def _candidates() -> list[dict]:
    c = _load_jsonl(CANDIDATES_JSONL)
    if not c:
        sys.exit(f"[ERROR] no candidates at {CANDIDATES_JSONL}")
    return c


# ---------------------------------------------------------------------------
# Light feature extraction (for the printed worksheet)
# ---------------------------------------------------------------------------

def _penalty(raw: str) -> str:
    t = raw.lower()
    m = re.search(r"\b(\d+)\s*second\s*time penalty", t) or re.search(r"\b(\d+)\s*s(?:ec)?\s*time penalty", t)
    if m:
        return f"{m.group(1)}s time penalty"
    for needle, slug in [
        ("no further action", "no further action"), ("disqualif", "disqualified"),
        ("drive-through", "drive-through"), ("drive through", "drive-through"),
        ("stop-and-go", "stop-and-go"), ("stop and go", "stop-and-go"),
        ("reprimand", "reprimand"), ("grid drop", "grid drop"),
        ("grid penalty", "grid penalty"), ("grid place", "grid drop"),
        ("pit lane start", "pit-lane start"), ("time penalty", "time penalty"),
    ]:
        if needle in t:
            return slug
    if re.search(r"fined?\s*[€$]", t):
        return "fine"
    return "?"


def _fact(raw: str) -> str:
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw.split("\n")]
    lines = [ln for ln in lines if ln]
    for i, ln in enumerate(lines):
        ll = ln.lower()
        if ll == "fact" or ll.startswith("fact "):
            c = ln[5:].strip() if ll.startswith("fact ") else ""
            if not c and i + 1 < len(lines):
                c = lines[i + 1]
            return c[:200]
    m = re.search(r"determine the following[:\s]+(.{20,200})", raw, re.I)
    return m.group(1).strip()[:200] if m else ""


def _why(raw: str, n: int = 320) -> str:
    """Stewards' rationale — the text after 'Reason' (boilerplate stripped)."""
    text = re.sub(r"\s+", " ", raw)
    m = re.search(r"\bReason\b[:\s]+(.+)", text, re.I)
    if not m:
        return ""
    why = m.group(1)
    # cut the standard appeal boilerplate that ends most decisions
    why = re.split(r"Competitors are reminded|Decisions of the Stewards are taken", why)[0]
    return why.strip()[:n]


def _decision(raw: str) -> str:
    """The stewards' decision line(s) — captures penalty + penalty points."""
    text = re.sub(r"[ \t]+", " ", raw)
    m = re.search(r"\bDecision\b[:\s]+(.+?)\n\s*Reason\b", text, re.I | re.S)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:140]
    return ""


# ---------------------------------------------------------------------------
# --print
# ---------------------------------------------------------------------------

def do_print(start: int, count: int) -> None:
    cands = _candidates()
    idx = _index()
    end = min(start + count, len(cands))
    print(f"# PAIRS [{start}:{end}] of {len(cands)} total\n")
    for i in range(start, end):
        c = cands[i]
        a, b = idx.get(c["anchor_id"]), idx.get(c["other_id"])
        if not a or not b:
            print(f"### PAIR {i} | MISSING DOC — skip\n")
            continue
        ra, rb = a.get("raw_text", ""), b.get("raw_text", "")
        print(f"### PAIR {i} | stage1={c['label']} | bucket={c.get('offence_type','?')}")
        for tag, rec, raw in (("A", a, ra), ("B", b, rb)):
            print(f"{tag} [{rec.get('season')}] {rec.get('title','')}")
            print(f"   FACT: {_fact(raw) or '(none)'}")
            dec = _decision(raw)
            print(f"   DECISION: {dec or _penalty(raw)}")
            why = _why(raw)
            if why:
                print(f"   WHY: {why}")
        print("=" * 70)


# ---------------------------------------------------------------------------
# --ingest
# ---------------------------------------------------------------------------

def do_ingest(path: str) -> None:
    verdicts = json.loads(Path(path).read_text())
    cands = _candidates()
    existing = {r["i"]: r for r in _load_jsonl(ADJUDICATED_JSONL)}
    n_new = 0
    for v in verdicts:
        i = v["i"]
        if not (0 <= i < len(cands)):
            print(f"  [warn] index {i} out of range — skipped")
            continue
        if v["v"] not in ("similar", "dissimilar", "drop"):
            print(f"  [warn] index {i} bad verdict {v['v']!r} — skipped")
            continue
        c = cands[i]
        existing[i] = {
            "i": i,
            "anchor_id": c["anchor_id"],
            "other_id": c["other_id"],
            "stage1": c["label"],
            "v": v["v"],
            "c": v.get("c", "med"),
            "r": v.get("r", ""),
        }
        n_new += 1
    rows = [existing[k] for k in sorted(existing)]
    with ADJUDICATED_JSONL.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  ingested {n_new} verdicts → {len(rows)} total in {ADJUDICATED_JSONL.name}")


# ---------------------------------------------------------------------------
# --status
# ---------------------------------------------------------------------------

def do_status() -> None:
    cands = _candidates()
    done = {r["i"] for r in _load_jsonl(ADJUDICATED_JSONL)}
    total = len(cands)
    missing = [i for i in range(total) if i not in done]
    print(f"adjudicated: {len(done)}/{total}   remaining: {len(missing)}")
    if missing:
        # print contiguous ranges of remaining indices
        lo = missing[0]
        prev = missing[0]
        ranges = []
        for x in missing[1:]:
            if x != prev + 1:
                ranges.append((lo, prev))
                lo = x
            prev = x
        ranges.append((lo, prev))
        print("  remaining ranges:", ", ".join(f"{a}-{b}" for a, b in ranges))


# ---------------------------------------------------------------------------
# --finalize
# ---------------------------------------------------------------------------

def do_finalize() -> None:
    idx = _index()
    rows = _load_jsonl(ADJUDICATED_JSONL)
    if not rows:
        sys.exit("[ERROR] nothing adjudicated yet.")

    accepted: list[dict] = []   # high-confidence agreements → locked training data
    queue: list[dict] = []      # flips + low-confidence + drops → human Stage 2b

    n_agree = n_flip = n_low = n_drop = 0
    for r in rows:
        v, conf, stage1 = r["v"], r.get("c", "med"), r["stage1"]
        a, b = idx.get(r["anchor_id"]), idx.get(r["other_id"])
        if not a or not b:
            continue
        flip = (v != stage1) and v in ("similar", "dissimilar")
        drop = v == "drop"
        low = conf == "low"
        if flip:
            n_flip += 1
        if low:
            n_low += 1
        if drop:
            n_drop += 1

        flagged = flip or low or drop
        if flagged:
            note = "DROP?" if drop else ("FLIP→" + v if flip else "LOW")
            queue.append({
                "anchor_id": r["anchor_id"],
                "other_id": r["other_id"],
                # proposal the human sees = AI verdict (fall back to stage1 for drops)
                "label": v if v in ("similar", "dissimilar") else stage1,
                "reason": f"[AI {note} | conf={conf}] {r.get('r','')}",
                "offence_type": "adjudication-flagged",
            })
        else:
            n_agree += 1
            accepted.append({
                "anchor_id": r["anchor_id"],
                "positive_id": r["other_id"] if v == "similar" else None,
                "negative_id": r["other_id"] if v == "dissimilar" else None,
                "label": v,
                "anchor_title": a.get("title"),
                "other_title": b.get("title"),
                "anchor_season": a.get("season"),
                "other_season": b.get("season"),
            })

    with OUTPUT_JSONL.open("w", encoding="utf-8") as f:
        for r in accepted:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with REVIEW_QUEUE_JSONL.open("w", encoding="utf-8") as f:
        for r in queue:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    asim = sum(1 for r in accepted if r["label"] == "similar")
    adis = sum(1 for r in accepted if r["label"] == "dissimilar")
    print(f"\nAdjudicated rows     : {len(rows)}")
    print(f"  agree (auto-accept): {n_agree}   ({asim} similar / {adis} dissimilar)")
    print(f"  flips              : {n_flip}")
    print(f"  low-confidence     : {n_low}")
    print(f"  drops              : {n_drop}")
    print(f"\nLocked training data → {OUTPUT_JSONL.name}  ({len(accepted)} pairs)")
    print(f"Human review queue   → {REVIEW_QUEUE_JSONL.name}  ({len(queue)} pairs)")
    print(f"\nHuman Stage 2b:\n  python scripts/review_pairs.py --candidates {REVIEW_QUEUE_JSONL}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="AI adjudication harness")
    p.add_argument("--print", dest="do_print", action="store_true")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--count", type=int, default=40)
    p.add_argument("--ingest", metavar="PATH")
    p.add_argument("--status", action="store_true")
    p.add_argument("--finalize", action="store_true")
    args = p.parse_args()

    if args.do_print:
        do_print(args.start, args.count)
    elif args.ingest:
        do_ingest(args.ingest)
    elif args.status:
        do_status()
    elif args.finalize:
        do_finalize()
    else:
        p.print_help()


if __name__ == "__main__":
    main()
