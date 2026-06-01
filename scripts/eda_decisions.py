"""
Quick EDA on scraped decisions data — run after scraping seasons.

Prints summary stats: total records, by-season counts, infraction distribution,
outcome distribution, OCR rate.

Usage:
    python scripts/eda_decisions.py
    python scripts/eda_decisions.py --output data/eda_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DECISIONS_PATH = ROOT / "data" / "parsed" / "decisions.jsonl"


def load_records(path: Path) -> list[dict]:
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def run_eda(records: list[dict]) -> dict:
    from packages.pipeline.parsers.decision_parser import batch_extract

    print("\nRACEJUDGE — Decision Data EDA")
    print(f"{'=' * 50}")
    print(f"Total records: {len(records)}")

    # Season distribution
    seasons = Counter(r.get("season") for r in records)
    print("\nBy season:")
    for season in sorted(k for k in seasons if k is not None):
        print(f"  {season}: {seasons[season]:4d}")

    # OCR rate
    needs_ocr = sum(1 for r in records if r.get("needs_ocr"))
    print(f"\nOCR needed: {needs_ocr}/{len(records)} ({needs_ocr/len(records)*100:.1f}%)")

    # Char count distribution
    char_counts = [r.get("char_count", 0) for r in records]
    avg_chars = sum(char_counts) / max(len(char_counts), 1)
    empty = sum(1 for c in char_counts if c == 0)
    print(f"Avg chars/doc: {avg_chars:.0f}")
    print(f"Empty docs (0 chars): {empty}")

    # Parser version distribution
    versions = Counter(r.get("parser_version") for r in records)
    print("\nParser versions:")
    for v, n in versions.most_common():
        print(f"  {v}: {n}")

    # Run decision parser on sample to get infraction/outcome stats
    print("\nRunning structured extraction on all records...")
    extracted = batch_extract(records)

    # Infraction type distribution
    infractions = Counter(e.get("infraction_type") for e in extracted if e.get("infraction_type"))
    print(f"\nTop 10 infraction types (out of {len(infractions)} unique):")
    for infraction, count in infractions.most_common(10):
        print(f"  {infraction}: {count}")

    # Outcome distribution
    outcomes = Counter(e.get("outcome") for e in extracted if e.get("outcome"))
    print(f"\nTop 10 outcomes (out of {len(outcomes)} unique):")
    for outcome, count in outcomes.most_common(10):
        print(f"  {outcome}: {count}")

    # Session type distribution
    sessions = Counter(e.get("session_type") for e in extracted if e.get("session_type"))
    print("\nSession types:")
    for session, count in sessions.most_common():
        print(f"  {session}: {count}")

    # Extraction coverage
    fields = ["car_number", "driver_name", "infraction_type", "outcome", "lap_number"]
    print("\nExtraction coverage (% of docs):")
    for field in fields:
        count = sum(1 for e in extracted if e.get(field) is not None)
        print(f"  {field}: {count}/{len(extracted)} ({count/len(extracted)*100:.1f}%)")

    return {
        "total_records": len(records),
        "by_season": dict(seasons),
        "needs_ocr": needs_ocr,
        "avg_chars": round(avg_chars),
        "top_infractions": dict(infractions.most_common(20)),
        "top_outcomes": dict(outcomes.most_common(20)),
        "session_types": dict(sessions),
        "extraction_coverage": {
            f: sum(1 for e in extracted if e.get(f) is not None) / len(extracted)
            for f in fields
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="EDA on decisions.jsonl")
    parser.add_argument("--output", type=Path, help="Write report JSON to this path")
    args = parser.parse_args()

    if not DECISIONS_PATH.exists():
        print(f"Error: {DECISIONS_PATH} not found — run scraper first.")
        sys.exit(1)

    records = load_records(DECISIONS_PATH)
    report = run_eda(records)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport written to {args.output}")


if __name__ == "__main__":
    main()
