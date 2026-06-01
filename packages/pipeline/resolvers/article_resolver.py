"""
Article Resolver — Phase 2.

Maps raw article citations extracted from decision text to canonical
guideline rows in the guidelines table.

Input examples:
  "Art. 48.1", "Article 48.1", "Appendix L Chapter 4", "Art 2 of the
  International Sporting Code", "48.1 of the Sporting Regulations"

Output: list of {article_number, document_name, article_id (if in DB)}
"""

from __future__ import annotations

import re
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction patterns
# ---------------------------------------------------------------------------

# Standard article: "Art. 48.1", "Article 2.3", "art 55.13"
_ART_RE = re.compile(
    r"\bart(?:icle)?\.?\s*(\d{1,3}(?:\.\d{1,3})*)",
    re.IGNORECASE,
)

# Appendix: "Appendix L", "Appendix H Chapter 3"
_APPENDIX_RE = re.compile(
    r"\bappendix\s+([A-Z])(?:\s+(?:ch(?:apter)?\.?\s*(\d+)))?",
    re.IGNORECASE,
)

# Document hints in citation text
_DOC_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sporting\s+regulation",   re.IGNORECASE), "F1 Sporting Regulations"),
    (re.compile(r"technical\s+regulation",  re.IGNORECASE), "F1 Technical Regulations"),
    (re.compile(r"financial\s+regulation",  re.IGNORECASE), "F1 Financial Regulations"),
    (re.compile(r"international\s+sporting", re.IGNORECASE), "ISC"),
    (re.compile(r"penalty\s+guideline",     re.IGNORECASE), "FIA Penalty Guidelines"),
    (re.compile(r"driving\s+standard",      re.IGNORECASE), "Driving Standards Guidelines"),
]

# Known canonical article → document mapping (from seed data)
ARTICLE_DOC_MAP: dict[str, str] = {
    "38.1":  "FIA Penalty Guidelines",
    "38.2":  "FIA Penalty Guidelines",
    "33.3":  "F1 Sporting Regulations",
    "34.7":  "F1 Sporting Regulations",
    "34.12": "F1 Sporting Regulations",
    "20.5":  "F1 Sporting Regulations",
    "48.1":  "F1 Sporting Regulations",
    "55.13": "F1 Sporting Regulations",
    "55.14": "F1 Sporting Regulations",
    "2.1":   "ISC",
    "12.1":  "ISC",
    "12.2":  "ISC",
}


# ---------------------------------------------------------------------------
# Citation record
# ---------------------------------------------------------------------------

class ArticleCitation:
    __slots__ = ("article_number", "document_name", "raw_text", "article_id")

    def __init__(
        self,
        article_number: str,
        document_name: str,
        raw_text: str = "",
        article_id: str | None = None,
    ):
        self.article_number = article_number
        self.document_name  = document_name
        self.raw_text       = raw_text
        self.article_id     = article_id

    def to_dict(self) -> dict:
        return {
            "article_number": self.article_number,
            "document_name":  self.document_name,
            "raw_text":       self.raw_text,
            "article_id":     self.article_id,
        }

    def __repr__(self) -> str:
        return f"ArticleCitation({self.article_number!r} @ {self.document_name!r})"


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class ArticleResolver:
    """
    Extract and resolve article citations from decision text.

    Usage:
        resolver = ArticleResolver()
        citations = resolver.extract("...pursuant to Art. 48.1 of the Sporting Regulations...")
        # → [ArticleCitation("48.1", "F1 Sporting Regulations")]

        # With DB lookup:
        citations = await resolver.resolve_with_db(text, db_session)
    """

    def extract(self, text: str) -> list[ArticleCitation]:
        """
        Extract all article citations from text.
        Does not require DB — returns citations with article_id=None.
        """
        if not text:
            return []

        citations: list[ArticleCitation] = []
        seen: set[str] = set()

        # Find document context near each citation
        def _infer_document(pos: int) -> str:
            window = text[max(0, pos - 100): pos + 100]
            for pattern, doc_name in _DOC_HINTS:
                if pattern.search(window):
                    return doc_name
            return ""

        # Standard article numbers
        for m in _ART_RE.finditer(text):
            article_num = m.group(1)
            key = f"art:{article_num}"
            if key in seen:
                continue
            seen.add(key)

            doc = _infer_document(m.start())
            if not doc:
                doc = ARTICLE_DOC_MAP.get(article_num, "F1 Sporting Regulations")

            citations.append(ArticleCitation(
                article_number=article_num,
                document_name=doc,
                raw_text=m.group(0),
            ))

        # Appendix references
        for m in _APPENDIX_RE.finditer(text):
            letter  = m.group(1).upper()
            chapter = m.group(2)
            article_num = f"Appendix {letter}"
            if chapter:
                article_num += f" Ch.{chapter}"
            key = f"app:{article_num}"
            if key in seen:
                continue
            seen.add(key)

            citations.append(ArticleCitation(
                article_number=article_num,
                document_name="F1 Sporting Regulations",
                raw_text=m.group(0),
            ))

        return citations

    def extract_strings(self, text: str) -> list[str]:
        """Convenience: return just article number strings."""
        return [c.article_number for c in self.extract(text)]

    async def resolve_with_db(self, text: str, db) -> list[ArticleCitation]:
        """
        Extract citations then look up article_id in the guidelines table.
        db: AsyncSession
        """
        citations = self.extract(text)
        if not citations:
            return []

        try:
            from sqlalchemy import select
            from packages.db.models import Guideline

            article_nums = [c.article_number for c in citations]
            result = await db.execute(
                select(Guideline.article_number, Guideline.article_id)
                .where(Guideline.article_number.in_(article_nums))
            )
            db_map: dict[str, str] = {row.article_number: row.article_id
                                       for row in result.all()}

            for c in citations:
                c.article_id = db_map.get(c.article_number)
        except Exception as exc:
            log.warning("ArticleResolver DB lookup failed: %s", exc)

        return citations
