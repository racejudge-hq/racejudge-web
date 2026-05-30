"""
Batch enrich decisions.jsonl with structured extraction.

Reads data/parsed/decisions.jsonl, runs decision_parser + text_cleaner
on each record, and writes enriched records to data/parsed/decisions_enriched.jsonl.

Usage:
    python scripts/enrich_decisions.py
    python scripts/enrich_decisions.py --season 2024 --output data/parsed/2024_enriched.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DECISIONS_PATH = ROOT / "data" / "parsed" / "decisions.jsonl"
ENRICHED_PATH = ROOT / "data" / "parsed" / "decisions_enriched.jsonl"


def enrich_record(record: dict) -> dict:
    from packages.pipeline.parsers.decision_parser import extract_incident
    from packages.pipeline.parsers.text_cleaner import (
        clean_decision_text,
        extract_article_citations,
        extract_stewards_names,
    )

    raw_text = record.get("raw_text", "")
    cleaned_text = clean_decision_text(raw_text)

    extracted = extract_incident({**record, "raw_text": cleaned_text})
    articles = extract_article_citations(cleaned_text)
    stewards = extract_stewards_names(cleaned_text)

    return {
        **record,
        "cleaned_text": cleaned_text,
        "parsed": {
            **extracted,
            "article_citations": articles,
            "stewards": stewards,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich decisions with structured extraction")
    parser.add_argument("--season", type=int, help="Filter by season")
    parser.add_argument("--output", type=Path, default=ENRICHED_PATH)
    parser.add_argument("--input", type=Path, default=DECISIONS_PATH)
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found — run scraper first.")
        sys.exit(1)

    records = []
    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    if args.season and rec.get("season") != args.season:
                        continue
                    records.append(rec)
                except json.JSONDecodeError:
                    continue

    print(f"Enriching {len(records)} records...")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    enriched_count = 0

    with open(args.output, "w") as out:
        for i, rec in enumerate(records):
            if i % 100 == 0:
                print(f"  {i}/{len(records)}")
            try:
                enriched = enrich_record(rec)
                out.write(json.dumps(enriched, ensure_ascii=False) + "\n")
                enriched_count += 1
            except Exception as e:
                print(f"  Error on {rec.get('doc_id')}: {e}")
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Done. {enriched_count} records written to {args.output}")


if __name__ == "__main__":
    main()
