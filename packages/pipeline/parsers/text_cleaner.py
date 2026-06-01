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


def extract_article_citations(text: str) -> list[str]:
    """
    Extract all FIA article citations from decision text.
    e.g. "Article 38.1", "Art. 27.3", "Appendix L, Chapter IV"
    """
    pattern = re.compile(
        r"(?:Art(?:icle)?\.?\s*|Appendix\s+)(\w+(?:\.\w+)*(?:,\s*(?:Chapter|Section)\s*\w+)?)",
        re.IGNORECASE,
    )
    matches = [m.group(0).strip() for m in pattern.finditer(text)]
    # Deduplicate while preserving order
    seen: set[str] = set()
    result = []
    for m in matches:
        normalized = m.lower()
        if normalized not in seen:
            seen.add(normalized)
            result.append(m)
    return result
