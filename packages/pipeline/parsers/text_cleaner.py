"""
PDF text post-processing — Phase 2.

Cleans raw pdfplumber output for better regex extraction and future
LayoutLMv3 fine-tuning. FIA PDFs often have:
  - Header/footer boilerplate (page numbers, watermarks)
  - Split words due to hyphenation across lines
  - Inconsistent whitespace from column layout
  - FIA document number watermarks (e.g. "FIA F1 Document 12/2024")

Usage:
    from packages.pipeline.parsers.text_cleaner import clean_decision_text
    clean = clean_decision_text(raw_text)
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Patterns to strip
# ---------------------------------------------------------------------------

# FIA document number watermarks
_FIA_DOC_NUM_RE = re.compile(r"FIA\s+F1\s+Document\s+\d+/\d{4}", re.IGNORECASE)

# Page numbers: "Page 1 of 3", "- 1 -", standalone digits on own line
_PAGE_NUM_RE = re.compile(
    r"(?:^Page\s+\d+\s+of\s+\d+$|^-\s*\d+\s*-$|^\d+$)",
    re.MULTILINE | re.IGNORECASE,
)

# Fédération Internationale de l'Automobile boilerplate
_FIA_HEADER_RE = re.compile(
    r"Fédération\s+Internationale\s+de\s+l'Automobile.*?(?:\n|$)",
    re.IGNORECASE,
)

# "The Stewards of the Meeting" boilerplate
_STEWARD_HEADER_RE = re.compile(
    r"THE\s+STEWARDS\s+OF\s+THE\s+MEETING\s*\n?",
    re.IGNORECASE,
)

# Repeated dashes/underscores used as dividers
_DIVIDER_RE = re.compile(r"[-_]{5,}")

# Multiple blank lines → single blank line
_MULTI_BLANK_RE = re.compile(r"\n{3,}")

# Trailing/leading whitespace on each line
_LINE_SPACE_RE = re.compile(r"[ \t]+$", re.MULTILINE)

# Soft hyphen / line-continuation hyphen (word split across lines)
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n(\w)")

# Common FIA PDF artifacts: ligatures, encoding issues
_LIGATURE_MAP = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "–": "-",    # en dash
    "—": "-",    # em dash
    " ": " ",  # non-breaking space
    "’": "'",  # right single quotation mark
    "“": '"',  # left double quotation mark
    "”": '"',  # right double quotation mark
}


# ---------------------------------------------------------------------------
# Main cleaner
# ---------------------------------------------------------------------------

def clean_decision_text(text: str) -> str:
    """
    Post-process raw PDF text for cleaner regex extraction.
    Preserves document structure (headings, lists) while removing artifacts.
    """
    if not text:
        return text

    # Fix ligatures and encoding artifacts
    for bad, good in _LIGATURE_MAP.items():
        text = text.replace(bad, good)

    # Rejoin soft-hyphenated words split across lines
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)

    # Strip FIA watermarks and headers
    text = _FIA_DOC_NUM_RE.sub("", text)
    text = _FIA_HEADER_RE.sub("", text)
    text = _STEWARD_HEADER_RE.sub("", text)

    # Remove page numbers
    text = _PAGE_NUM_RE.sub("", text)

    # Remove dividers
    text = _DIVIDER_RE.sub("", text)

    # Strip trailing whitespace from each line
    text = _LINE_SPACE_RE.sub("", text)

    # Collapse multiple blank lines
    text = _MULTI_BLANK_RE.sub("\n\n", text)

    return text.strip()


def normalize_decision_title(title: str) -> str:
    """
    Normalize a decision title for display and indexing.
    Removes common suffixes added by the FIA website.
    """
    # Strip "Published on DD Month YYYY" suffix
    title = re.sub(
        r"\s*[-–]\s*Published on \d{1,2} \w+ \d{4}\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    # Strip trailing dashes or underscores
    title = title.strip(" -_")
    return title.strip()


def extract_stewards_names(text: str) -> list[str]:
    """
    Extract steward names from the signature block.
    Returns list of names (usually 3-4 stewards + one driver steward).
    """
    # Stewards sign at the bottom, typically:
    # "The Stewards:\nFirst Steward\nSecond Steward\nDriver Steward (Driver)"
    m = re.search(
        r"(?:The\s+)?Stewards?[:\s]*\n((?:[A-Z][a-zA-Z\s\-\.]+\n?){1,6})",
        text,
        re.IGNORECASE,
    )
    if not m:
        return []
    raw = m.group(1)
    names = [n.strip() for n in raw.splitlines() if n.strip() and len(n.strip()) > 3]
    return names[:5]  # max 5 stewards


_ARTICLE_RE = re.compile(
    # "Art 15", "Art. 27.3", "Article 12.4.1.e", "Articles 2", "Article B1.6.3a",
    # "Article 2c" (Appendix L's driving-standards articles carry a bare letter).
    r"\bArt(?:icle)?s?\.?\s*(?P<article>[A-Z]?\d+(?:\.[0-9A-Za-z]+)*(?:[a-z](?![a-z]))?"
    # "Articles 28.2 and 29.2", "Articles 40.3, 40.6" -- one prefix, several
    # articles. Only the first was ever recorded; the rest were dropped.
    r"(?:\s*(?:,|and)\s*\d+(?:\.\d+)*(?:[a-z](?![a-z]))?)*)"
    # "Appendix L", "Appendix H", "Appendix 1", each optionally with its chapter.
    r"|\bAppendix\s+(?P<appendix>[A-Z](?![a-z])|\d+)"
    r"(?P<chapter>\s*,?\s*(?:Chapter|Section)\s+[IVXLCDM0-9]+)?",
    re.IGNORECASE,
)

# The separator before a paragraph letter: "12.4.1.e" -> "12.4.1e". Only after a
# digit, so "B1.6.2b.i" is left alone. See extract_article_citations.
_PARA_DOT_RE = re.compile(r"(?<=\d)\.(?=[a-z]$)")


def extract_article_citations(text: str) -> list[str]:
    """Return the FIA articles a decision cites, normalised: "38.1", "Appendix L".

    Two things here are load-bearing.

    The leading `\\b` is the whole reason this was rewritten. Without it `Art`
    matched inside ordinary words, and a quarter of every citation in the
    database was debris: `artin` 402 times from steward *Martin*, plus `arts`,
    `arties`, `articular`, `articipates`, `arting`, `artment`. 191 documents
    had nothing stored but debris.

    Requiring a number after the prefix is the other half. `Art` on its own,
    or the bare word `Articles`, cites nothing -- and a rule that only accepts
    a real article number cannot resurrect the word-fragment problem by a
    different route.

    The chapter comma is optional because the corpus writes it both ways:
    "Appendix L, Chapter IV" and "Appendix L Chapter IV" are the same citation
    and must not become two.

    The dot before a paragraph letter goes the same way, and for the same
    reason: the corpus writes "Article 12.4.1.e" 86 times and "Article 12.4.1e"
    9 times, and this column exists to group precedents by the article they
    cite. Four articles were split across two spellings of themselves. Only the
    separator is dropped, and only after a digit -- "B1.6.2b.i" keeps its dot,
    because there the letter before it is part of the article, not a number.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(ref: str) -> None:
        ref = _PARA_DOT_RE.sub("", ref)
        key = ref.lower()
        if key not in seen:
            seen.add(key)
            out.append(ref)

    for m in _ARTICLE_RE.finditer(text):
        article = m.group("article")
        if article:
            for part in re.split(r"\s*(?:,|and)\s*", article):
                if part:
                    add(part.rstrip("."))
            continue

        ref = "Appendix " + m.group("appendix").upper()
        chapter = m.group("chapter")
        if chapter:
            # Collapse the newlines the PDFs wrap citations across.
            ref += ", " + re.sub(r"^[\s,]*", "", " ".join(chapter.split()))
        add(ref)
    return out
