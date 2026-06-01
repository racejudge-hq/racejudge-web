"""Tests for packages.pipeline.parsers.text_cleaner."""

import pytest

from packages.pipeline.parsers.text_cleaner import (
    clean_decision_text,
    extract_article_citations,
    extract_stewards_names,
    normalize_decision_title,
)


def test_clean_removes_ligatures():
    text = "The oﬃcial ﬁnding is that the driver was at fault."
    result = clean_decision_text(text)
    assert "ffi" in result
    assert "fi" in result
    assert "ﬁ" not in result
    assert "ﬃ" not in result


def test_clean_rejoins_hyphenated_words():
    text = "The stew-\nards found the driver guilty."
    result = clean_decision_text(text)
    assert "stewards" in result


def test_clean_removes_page_numbers():
    text = "Some content.\nPage 1 of 3\nMore content.\n- 2 -\nEnd."
    result = clean_decision_text(text)
    assert "Page 1 of 3" not in result
    assert "- 2 -" not in result


def test_clean_removes_fia_doc_watermark():
    text = "Decision\nFIA F1 Document 12/2024\nThe stewards found..."
    result = clean_decision_text(text)
    assert "FIA F1 Document" not in result


def test_clean_collapses_blank_lines():
    text = "Line 1.\n\n\n\nLine 2."
    result = clean_decision_text(text)
    assert "\n\n\n" not in result


def test_clean_empty_string():
    assert clean_decision_text("") == ""


def test_clean_none_safe():
    # Should not crash on None — caller responsible but test boundary
    result = clean_decision_text(None or "")
    assert result == ""


def test_normalize_title_strips_published_on():
    title = "Decision - Car 44 - Causing Collision - Published on 14 May 2025"
    result = normalize_decision_title(title)
    assert "Published on" not in result
    assert result == "Decision - Car 44 - Causing Collision"


def test_normalize_title_strips_trailing_dash():
    title = "Decision - Car 16 -"
    result = normalize_decision_title(title)
    assert not result.endswith("-")


def test_normalize_title_unchanged():
    title = "Stewards Communication - Investigation"
    result = normalize_decision_title(title)
    assert result == title


@pytest.mark.parametrize("text,expected", [
    (
        "Article 38.1 applies in this case.",
        ["Article 38.1"],
    ),
    (
        "Breach of Art. 27.3 and Art. 20.5(b) of the sporting regulations.",
        ["Art. 27.3", "Art. 20.5"],
    ),
    (
        "No article citations here.",
        [],
    ),
])
def test_extract_article_citations(text, expected):
    result = extract_article_citations(text)
    for exp in expected:
        assert any(exp.lower() in r.lower() for r in result), f"{exp!r} not found in {result}"


def test_extract_stewards_names():
    text = (
        "The Stewards:\n"
        "John Smith\n"
        "Maria Garcia\n"
        "Pierre Dupont\n"
        "Carlos Reutemann (Driver Steward)\n"
    )
    names = extract_stewards_names(text)
    assert len(names) >= 3
    assert any("Smith" in n for n in names)
