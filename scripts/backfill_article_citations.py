"""
Re-extract incidents.article_cited over the whole corpus.

A quarter of every citation in the column is not a citation. The old pattern
began `(?:Art(?:icle)?\\.?\\s*|Appendix\\s+)` with no leading word boundary, so
`Art` matched inside ordinary words, and `_normalize_article` returned its input
unchanged when it found no article number -- so the fragment went to the
database as a cited FIA article. Steward *Martin*'s surname alone put `artin`
there 402 times, joined by `art the`, `art of`, `arts`, `arties`, `articular`,
`articipates`, `arting` and `artment`. 194 incidents cite nothing else.

Both halves are fixed in text_cleaner.extract_article_citations and
incident_extractor._normalize_article. This applies the fix to the rows already
stored, which the pipeline will not revisit on its own.

Nothing is re-parsed from a PDF. Every incident is v2.0-layer1, meaning its
citations were read from decisions.raw_text by the same two functions this
script calls, so the recomputation is exactly what the fixed extractor would
have produced the first time.

Measured against the live corpus before writing:

    old  5,097 references, 1,254 of them fragments (24.6%)
    new  3,855 references,     0 fragments

180 references are *recovered*, not lost: "Articles 28.2 and 29.2" names two
articles and only the first was ever recorded. The 117 dropped occurrences are
all correct -- 110 bare `Appendix L` become the fuller `Appendix L, Chapter IV`,
`1` and `2` become `Appendix 1` and `Appendix 2`, and `11.00` was a time.

Usage:
    python scripts/backfill_article_citations.py --dry-run
    python scripts/backfill_article_citations.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from packages.pipeline.extractors.incident_extractor import (  # noqa: E402
    _normalize_article,
)
from packages.pipeline.parsers.text_cleaner import (  # noqa: E402
    clean_decision_text,
    extract_article_citations,
)

DB = os.environ["DATABASE_URL"].replace("+asyncpg", "")

SOURCE = """
SELECT i.incident_id, i.article_cited, d.raw_text
  FROM incidents i
  JOIN decisions d ON d.doc_id = i.doc_id
 ORDER BY i.incident_id
"""


def citations_for(raw_text: str) -> list[str]:
    """Recompute one incident's articles the way the extractor now does.

    Calls the pipeline's own functions rather than restating the rule, so this
    script cannot drift away from what the extractor writes.
    """
    cleaned = clean_decision_text(raw_text or "")
    found = extract_article_citations(cleaned)
    normalised = [n for a in found if a and (n := _normalize_article(a))]
    return list(dict.fromkeys(normalised))


def is_fragment(ref: str) -> bool:
    """A stored value that names no article: a word `Art` matched inside.

    `Appendix L` and `Appendix H` carry no digit and are real, so a digit test
    alone would condemn them.
    """
    if ref.lower().startswith("appendix"):
        return False
    return not any(ch.isdigit() for ch in ref)


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-extract incidents.article_cited")
    ap.add_argument("--dry-run", action="store_true", help="Report, write nothing")
    ap.add_argument(
        "--backup",
        type=Path,
        help="Write the current column to this JSON file before updating",
    )
    args = ap.parse_args()

    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute(SOURCE)
    rows = cur.fetchall()
    print(f"{len(rows)} incidents with source text", flush=True)

    updates: list[tuple[list[str], str]] = []
    backup: dict[str, list[str] | None] = {}
    old_refs = new_refs = old_frags = new_frags = 0
    emptied = 0
    gained: Counter[str] = Counter()
    lost: Counter[str] = Counter()

    for incident_id, stored, raw_text in rows:
        old = list(stored or [])
        new = citations_for(raw_text)
        backup[incident_id] = stored

        old_refs += len(old)
        new_refs += len(new)
        old_frags += sum(1 for r in old if is_fragment(r))
        new_frags += sum(1 for r in new if is_fragment(r))
        if old and not new:
            emptied += 1
        for r in set(new) - set(old):
            gained[r] += 1
        for r in set(old) - set(new):
            lost[r] += 1

        if new != old:
            updates.append((new, incident_id))

    pct = 100 * old_frags / old_refs if old_refs else 0
    print(f"  stored now : {old_refs:5d} references, {old_frags:4d} fragments ({pct:.1f}%)")
    pct = 100 * new_frags / new_refs if new_refs else 0
    print(f"  after fix  : {new_refs:5d} references, {new_frags:4d} fragments ({pct:.1f}%)")
    print(f"  rows to update            : {len(updates)}")
    print(f"  rows left citing nothing  : {emptied}")
    print(f"  gained: {sum(gained.values())} occurrences, {len(gained)} distinct")
    print("    " + ", ".join(f"{k} x{n}" for k, n in gained.most_common(8)))
    print(f"  lost  : {sum(lost.values())} occurrences, {len(lost)} distinct")
    print("    " + ", ".join(f"{k!r} x{n}" for k, n in lost.most_common(8)))

    if args.backup:
        args.backup.write_text(json.dumps({
            "taken_at": datetime.now(UTC).isoformat(),
            "column": "incidents.article_cited",
            "rows": backup,
        }, indent=1))
        print(f"\nprevious values saved to {args.backup}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return

    cur.executemany(
        "UPDATE incidents SET article_cited = %s WHERE incident_id = %s", updates
    )
    conn.commit()
    cur.execute("""
        SELECT count(*), coalesce(sum(array_length(article_cited, 1)), 0)
          FROM incidents WHERE article_cited <> '{}'
    """)
    rows_left, refs = cur.fetchone()
    print(f"\n{rows_left} incidents now cite {refs} articles between them")
    conn.close()


if __name__ == "__main__":
    main()
