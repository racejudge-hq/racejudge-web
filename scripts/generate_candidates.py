#!/usr/bin/env python3
"""
Stage 1 — AI candidate pair generator for RaceJudge BGE-M3 fine-tuning.

Reads : data/parsed/decisions.jsonl  (1,606 FIA stewards' decisions)
Writes: data/annotations/candidates.jsonl  (~360 labelled candidate pairs)

Label proposals — a human adjudicates them in Stage 2 via review_pairs.py:
  similar    — same bucket, same or comparable outcome/circumstances
  dissimilar — (a) cross-bucket easy negatives  ~⅔ of dissimilar
               (b) same-bucket hard negatives (different severity/outcome) ~⅓

Usage (from repo root with venv active):
    python scripts/generate_candidates.py
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

random.seed(42)

ROOT   = Path(__file__).resolve().parent.parent
INPUT  = ROOT / "data" / "parsed" / "decisions.jsonl"
OUTPUT = ROOT / "data" / "annotations" / "candidates.jsonl"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 1.  LOAD & FILTER
# ══════════════════════════════════════════════════════════════════════════════

def load_decisions(path: Path) -> list[dict]:
    decisions: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            rt = (d.get("raw_text") or "").strip()
            # Skip: summons, near-empty stubs, OCR-failed shells
            if len(rt) < 280:
                continue
            if d.get("needs_ocr") and len(rt) < 600:
                continue
            decisions.append(d)
    return decisions


print("Loading decisions …")
all_decisions = load_decisions(INPUT)
print(f"  {len(all_decisions)} usable decisions (summons/stubs filtered)")

# ══════════════════════════════════════════════════════════════════════════════
# 2.  BUCKET CLASSIFIER  (priority order — most specific pattern first)
# ══════════════════════════════════════════════════════════════════════════════

PATTERNS: list[tuple[str, list[str]]] = [
    # --- 1. Unsafe release (pit lane / garage) ---
    ("unsafe_release", [
        "unsafe release",
        "released from the garage into",
        "released in an unsafe",
        "release of the car was unsafe",
        "released into the path",
        "released the car into",
    ]),

    # --- 2. Blue flags ---
    ("ignoring_blue_flags", [
        "blue flag",
        "blue flags",
        "ignoring blue",
    ]),

    # --- 3. Pit-lane speeding (speed-limit breach in lane) ---
    ("pit_lane_speeding", [
        "pit lane speed",
        "pit-lane speed",
        "exceeded the pit lane speed limit",
        "pit lane speeding",
        "pit-lane speeding",
    ]),

    # --- 4. Collision ---
    ("causing_a_collision", [
        "collided with car",
        "collision with car",
        "wholly to blame",
        "predominantly to blame",
        "caused a collision",
        "caused the collision",
        "causing a collision",
        "car collided with car",
        "car collided with the car",
        "incident with car",
    ]),

    # --- 5. Forcing off ---
    ("forcing_another_driver_off", [
        "forced car",
        "forced another car",
        "forced off the track",
        "forcing another driver off",
        "forcing car",
        "forcing another driver",
        "pushed car off",
        "drove car off",
        "pushed off the track",
        "forced the car off",
    ]),

    # --- 6. Track limits ---
    ("track_limits", [
        "track limits",
        "did not use the track at turn",
        "gained an advantage by leaving the track",
        "failed to use the track",
        "exceeded track limits",
        "left the track and gained",
        "leaving the track and gain",
        "leaving the track",
        "lasting advantage",
    ]),

    # --- 7. Impeding in qualifying ---
    ("impeding_in_qualifying", [
        "unnecessarily impeded",
        "allegedly impeded",
        "unnecessary impeding",
        "impeded car",
        "impeding",      # note: 'impede' does NOT substring-match 'impeding'
        "impeded",
    ]),

    # --- 8. Safety car / VSC / red-flag infringement ---
    ("safety_car_vsc_red_flag", [
        "vsc delta",
        "virtual safety car",
        "safety car delta",
        "driving unnecessarily slowly during vsc",
        "exceeded the vsc",
        "safety car line",
        "sc delta",
        "red flag infringement",
        "red flag restart",
        "red flag conditions",
        "under red flag",
        "overtaking under red",
        "under safety car",
        "overtaking under safety",
        "behind the safety car",
        "exceeded the sc",
        "safety-car procedure",
        "safety car procedure",
        "safety car ecu",
        "ecu minimum",
    ]),

    # --- 9. Grid procedure / false start ---
    ("false_start_grid_procedure", [
        "starting procedure infringement",
        "start from the pit lane",
        "failed to start the formation lap in the correct order",
        "out of position at safety car line",
        "jump start",
        "false start",
        "moved before the start signal",
        "moving before",
        "moved before the signal",
        "practice start",
        "grid procedure infringement",
    ]),

    # --- 10. Formation / reconnaissance lap ---
    ("formation_recon_lap", [
        "reconnaissance lap",
        "recon lap",
        "formation lap procedure",
        "time limit between the safety car lines",
        "exceeded the 1:",
        "formation lap",
    ]),

    # --- 11. Technical / parc fermé ---
    ("technical_parc_ferme", [
        "parc ferm",
        "technical delegate",
        "power unit element",
        "pu element",
        "fuel mass flow",
        "technical infringement",
        "not in compliance with the technical regulations",
        "changed under parc",
        "wheel cover",
        "car was not in conformity",
        "scrutineering",
        "drs infringement",
        "drs activation",
        "use of drs",
        "drs system",
    ]),

    # --- 12. Race-director / stewards instructions ---
    ("race_director_instructions", [
        "competition notes",
        "event notes",
        "failed to comply with the race director",
        "failing to follow the race director",
        "failed to follow the race director",
        "race director's event notes",
        "race director's instructions",
        "race director instructions",
        "failed to move",
    ]),

    # --- 13. Dangerous / erratic / yellow-flag ---
    ("dangerous_erratic_driving", [
        "double yellow flag",
        "double yellow",
        "failed to slow",
        "did not slow",
        "dangerous driving",
        "erratic driving",
        "unnecessarily slowly",
        "driving erratically",
        "erratic manner",
        "yellow flag",
        "rejoining unsafely",
        "rejoined unsafely",
        "rejoining the track",
        "re-joining the track",
    ]),
]

BUCKET_LABELS: dict[str, str] = {
    "unsafe_release":             "unsafe release (pit lane)",
    "ignoring_blue_flags":        "ignoring blue flags",
    "pit_lane_speeding":          "pit-lane speeding",
    "causing_a_collision":        "causing a collision",
    "forcing_another_driver_off": "forcing another driver off track",
    "track_limits":               "track limits / leaving the track & gaining an advantage",
    "impeding_in_qualifying":     "impeding in qualifying",
    "safety_car_vsc_red_flag":    "safety-car/VSC/red-flag infringement",
    "false_start_grid_procedure": "jump/false start or grid-procedure infringement",
    "formation_recon_lap":        "formation/reconnaissance-lap procedure",
    "technical_parc_ferme":       "technical / parc fermé infringement",
    "race_director_instructions": "failing to follow race-director or stewards' instructions",
    "dangerous_erratic_driving":  "dangerous/erratic/unnecessarily-slow driving",
}


def _match_buckets(text: str) -> str | None:
    for bucket, keywords in PATTERNS:
        for kw in keywords:
            if kw in text:
                return bucket
    return None


def classify(d: dict) -> str | None:
    # Classify by TITLE first. FIA titles are curated, single-offence and
    # specific ("Infringement - Car 20 - Leaving the track and gaining a lasting
    # advantage"), so they beat the body, which often mentions other offences in
    # passing (e.g. an impeding case that references blue flags). Only when the
    # title is uninformative do we fall back to the body text. Title-first both
    # lifts older-season coverage and prevents priority-order misfiling.
    by_title = _match_buckets((d.get("title") or "").lower())
    if by_title:
        return by_title
    return _match_buckets((d.get("raw_text") or "").lower())


bucketed: dict[str, list[dict]] = defaultdict(list)
unclassified = 0
for d in all_decisions:
    bkt = classify(d)
    if bkt:
        d["_bucket"] = bkt
        bucketed[bkt].append(d)
    else:
        unclassified += 1

print("\nBucket distribution:")
for b, items in sorted(bucketed.items(), key=lambda x: -len(x[1])):
    print(f"  {BUCKET_LABELS[b]:60s}  {len(items):4d}")
print(f"  {'(unclassified — skipped)':60s}  {unclassified:4d}")


# ══════════════════════════════════════════════════════════════════════════════
# 3.  FEATURE EXTRACTION  (ground every reason in raw_text)
# ══════════════════════════════════════════════════════════════════════════════

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_fact(raw_text: str) -> str:
    """Return the Fact: field content — the stewards' terse summary of events."""
    lines = [_norm(ln) for ln in raw_text.split("\n") if _norm(ln)]
    for i, ln in enumerate(lines):
        ll = ln.lower()
        if ll.startswith("fact ") or ll == "fact":
            content = ln[5:].strip() if ll.startswith("fact ") else ""
            if not content and i + 1 < len(lines):
                content = lines[i + 1]
            return content[:180].rstrip(".,")
    # Fallback: first substantive sentence after "determine the following"
    m = re.search(r"determine the following[:\s]+(.{20,150})", raw_text, re.I)
    if m:
        return m.group(1).strip()[:180].rstrip(".,")
    return ""


def get_penalty(raw_text: str) -> str:
    """Categorise the stewards' penalty into a short slug for comparison."""
    text = raw_text.lower()
    m = re.search(r"\b(\d+)\s*second\s*time penalty", text)
    if m:
        return f"time_{m.group(1)}s"
    m = re.search(r"\b(\d+)\s*s(?:ec)?\s*time penalty", text)
    if m:
        return f"time_{m.group(1)}s"
    if "no further action" in text:
        return "no_further_action"
    if "disqualif" in text:
        return "dsq"
    if "drive-through" in text or "drive through" in text:
        return "drive_through"
    if "stop-and-go" in text or "stop and go" in text:
        return "stop_and_go"
    if "time penalty" in text:
        return "time_penalty"
    if "reprimand" in text:
        return "reprimand"
    if "grid drop" in text or "grid penalty" in text or "grid place" in text:
        return "grid_drop"
    if "pit lane start" in text or "start from the pit lane" in text:
        return "pit_lane_start"
    if re.search(r"fined?\s*[€$]", text):
        return "fine"
    if "suspended" in text and "penalty" in text:
        return "suspended_penalty"
    return "other"


def get_session(raw_text: str) -> str:
    text = raw_text.lower()
    for sess in ("qualifying", "sprint", "practice", "race"):
        if f"session {sess}" in text or f"\n{sess}\n" in text:
            return sess
    return "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# 4.  PAIR MACHINERY
# ══════════════════════════════════════════════════════════════════════════════

candidates: list[dict] = []
seen: set[frozenset] = set()


def _add(a: dict, b: dict, label: str, reason: str, offence: str) -> bool:
    """Append pair if unseen. Truncates reason to ≤30 words. Returns True on success."""
    key = frozenset([a["doc_id"], b["doc_id"]])
    if key in seen or a["doc_id"] == b["doc_id"]:
        return False
    seen.add(key)
    words = reason.split()
    if len(words) > 30:
        reason = " ".join(words[:30])
    candidates.append({
        "anchor_id":    a["doc_id"],
        "other_id":     b["doc_id"],
        "label":        label,
        "reason":       reason,
        "offence_type": offence,
    })
    return True


def _bl(bucket: str) -> str:
    return BUCKET_LABELS.get(bucket, bucket.replace("_", " "))


def _sample(items: list[dict], n: int) -> list[dict]:
    """Random sample of min(n, len) items from list."""
    if len(items) <= n:
        return list(items)
    return random.sample(items, n)


def _stratified_pool(items: list[dict], per_season: int = 12) -> list[dict]:
    """Pool that takes up to `per_season` items from EACH season.

    Buckets are dominated by recent seasons (2023–2025), so a flat random
    sample buries the handful of 2019–2021 decisions and they never get paired.
    Capping per season guarantees every era enters the combination space, which
    both lifts old-season coverage and yields more cross-era (more valuable)
    similar pairs.
    """
    by_season: dict[int, list[dict]] = defaultdict(list)
    for d in items:
        by_season[d.get("season", 0)].append(d)
    pool: list[dict] = []
    for group in by_season.values():
        random.shuffle(group)
        pool.extend(group[:per_season])
    random.shuffle(pool)
    return pool


# ══════════════════════════════════════════════════════════════════════════════
# 4A.  SIMILAR PAIRS
#      Strategy: same bucket, prefer (a) cross-season and (b) same penalty.
#      Cap at MAX_PER_BUCKET so no single bucket dominates.
# ══════════════════════════════════════════════════════════════════════════════

MAX_SIM_PER_BUCKET = 22   # × 13 buckets = 286 ceiling; human prunes to ~180

def sim_score(a: dict, b: dict) -> int:
    pa, pb = get_penalty(a["raw_text"]), get_penalty(b["raw_text"])
    sa, sb = get_session(a["raw_text"]),  get_session(b["raw_text"])
    score  = 0
    if pa == pb and pa not in ("other", ""):
        score += 4   # same penalty → strongest similarity signal
    if sa == sb and sa != "unknown":
        score += 2   # same session type
    if a.get("season") != b.get("season"):
        score += 1   # cross-season → more diverse training data
    if a.get("char_count", 0) > 700 and b.get("char_count", 0) > 700:
        score += 1   # longer decisions → richer reasoning text for model
    return score


for bucket, items in sorted(bucketed.items()):
    if len(items) < 2:
        continue
    pool = _stratified_pool(items, per_season=12)   # every era in the pool
    scored: list[tuple[int, dict, dict]] = [
        (sim_score(da, db), da, db)
        for da, db in combinations(pool, 2)
    ]
    scored.sort(key=lambda x: -x[0])

    added = 0
    for _sc, da, db in scored:
        if added >= MAX_SIM_PER_BUCKET:
            break
        pa   = get_penalty(da["raw_text"])
        pb   = get_penalty(db["raw_text"])
        fa   = extract_fact(da["raw_text"])
        fb   = extract_fact(db["raw_text"])
        bl   = _bl(bucket)

        if pa == pb and pa not in ("other", ""):
            reason = (f"Both {bl}: same penalty ({pa.replace('_',' ')}) — "
                      f"{fa[:60]} / {fb[:60]}")
        else:
            reason = (f"Both {bl}: identical breach — "
                      f"{fa[:75]} / {fb[:75]}")

        if _add(da, db, "similar", reason, bl):
            added += 1

sim_count = sum(1 for c in candidates if c["label"] == "similar")
print(f"\nSimilar pairs generated   : {sim_count}")


# ══════════════════════════════════════════════════════════════════════════════
# 4B.  HARD NEGATIVES  — same bucket, materially different outcome
#      These are the highest training-value examples. Target ≈60; budget 8/bucket.
# ══════════════════════════════════════════════════════════════════════════════

HARD_TARGET      = 65
HARD_PER_BUCKET  = 8


def hard_score(a: dict, b: dict) -> int:
    pa, pb = get_penalty(a["raw_text"]), get_penalty(b["raw_text"])
    score  = 0
    if pa != pb:
        score += 3
    if "no_further_action" in (pa, pb):
        score += 2   # NFA vs any penalty is the clearest contrast
    if a.get("season") != b.get("season"):
        score += 1
    return score


hard_added = 0
for bucket, items in sorted(bucketed.items()):
    if hard_added >= HARD_TARGET:
        break
    if len(items) < 2:
        continue
    pool = _stratified_pool(items, per_season=12)
    scored = [
        (hard_score(da, db), da, db)
        for da, db in combinations(pool, 2)
        if get_penalty(da["raw_text"]) != get_penalty(db["raw_text"])
        and not all(p in ("other", "") for p in
                    [get_penalty(da["raw_text"]), get_penalty(db["raw_text"])])
    ]
    scored.sort(key=lambda x: -x[0])

    bucket_hard = 0
    for _sc, da, db in scored:
        if bucket_hard >= HARD_PER_BUCKET or hard_added >= HARD_TARGET:
            break
        pa  = get_penalty(da["raw_text"])
        pb  = get_penalty(db["raw_text"])
        fa  = extract_fact(da["raw_text"])
        fb  = extract_fact(db["raw_text"])
        bl  = _bl(bucket)
        reason = (f"Same {bl} but outcomes differ: "
                  f"{pa.replace('_',' ')} ({fa[:50]}) "
                  f"vs {pb.replace('_',' ')} ({fb[:50]})")
        if _add(da, db, "dissimilar", reason, bl):
            bucket_hard += 1
            hard_added  += 1

hard_count = hard_added
print(f"Hard negative pairs       : {hard_count}")


# ══════════════════════════════════════════════════════════════════════════════
# 4C.  EASY NEGATIVES  — cross-bucket, maximise bucket-pair diversity
#      Target ≈120
# ══════════════════════════════════════════════════════════════════════════════

EASY_TARGET = 125
easy_added  = 0

bucket_names = list(bucketed.keys())
random.shuffle(bucket_names)

flat: dict[str, list[dict]] = {bn: list(bucketed[bn]) for bn in bucket_names}
for _bk in flat:
    random.shuffle(flat[_bk])

# Enumerate every ordered bucket pair; repeat to hit target
bucket_pairs: list[tuple[str, str]] = [
    (b1, b2) for i, b1 in enumerate(bucket_names)
    for b2 in bucket_names[i + 1:]
]
random.shuffle(bucket_pairs)
pool_expanded = bucket_pairs * (EASY_TARGET // max(len(bucket_pairs), 1) + 2)
random.shuffle(pool_expanded)

attempts = 0
for b1, b2 in pool_expanded:
    if easy_added >= EASY_TARGET or attempts > 25_000:
        break
    attempts += 1
    if not flat.get(b1) or not flat.get(b2):
        continue
    a     = random.choice(flat[b1])
    b_doc = random.choice(flat[b2])
    key   = frozenset([a["doc_id"], b_doc["doc_id"]])
    if key in seen or a["doc_id"] == b_doc["doc_id"]:
        continue
    fa   = extract_fact(a["raw_text"])
    fb   = extract_fact(b_doc["raw_text"])
    bl1  = _bl(b1)
    bl2  = _bl(b2)
    reason = (f"Different offences: {bl1} ({fa[:42]}) "
              f"vs {bl2} ({fb[:42]})")
    if _add(a, b_doc, "dissimilar", reason, f"{bl1} vs {bl2}"):
        easy_added += 1

print(f"Easy negative pairs       : {easy_added}")


# ══════════════════════════════════════════════════════════════════════════════
# 5.  SUMMARY & SEASON SPREAD
# ══════════════════════════════════════════════════════════════════════════════

id_map    = {d["doc_id"]: d for d in all_decisions}
sim_total = sum(1 for c in candidates if c["label"] == "similar")
dis_total = sum(1 for c in candidates if c["label"] == "dissimilar")

print(f"\n{'─' * 62}")
print(f"Total candidates : {len(candidates)}  "
      f"({sim_total} similar / {dis_total} dissimilar)")

season_cnt: dict[int, int] = defaultdict(int)
for c in candidates:
    rec = id_map.get(c["anchor_id"])
    if rec:
        season_cnt[rec.get("season", 0)] += 1

print("Anchor-season spread:")
for season in sorted(season_cnt):
    bar = "█" * (season_cnt[season] // 3)
    print(f"  {season}  {season_cnt[season]:4d}  {bar}")


# ══════════════════════════════════════════════════════════════════════════════
# 6.  WRITE  (shuffle so review queue isn't all one bucket at a time)
# ══════════════════════════════════════════════════════════════════════════════

random.shuffle(candidates)

with OUTPUT.open("w", encoding="utf-8") as fh:
    for c in candidates:
        fh.write(json.dumps(c, ensure_ascii=False) + "\n")

print(f"\n✓  Wrote {len(candidates)} candidates → {OUTPUT}")
print("\nValidate with:")
print("  python scripts/review_pairs.py --validate")
