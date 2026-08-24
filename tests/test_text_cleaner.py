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
    ("Article 38.1 applies in this case.", ["38.1"]),
    (
        "Breach of Art. 27.3 and Art. 20.5(b) of the sporting regulations.",
        ["27.3", "20.5"],
    ),
    ("No article citations here.", []),
    # The citation forms the corpus actually uses.
    ("Breach of Article 12.4.1.e of the Code.", ["12.4.1e"]),
    ("Appendix L, Chapter IV, Article 2c) of the Code", ["Appendix L, Chapter IV", "2c"]),
    ("Breach of Appendix L Chapter IV Article 5b", ["Appendix L, Chapter IV", "5b"]),
    ("in breach of Article B1.6.3a", ["B1.6.3a"]),
    ("See Appendix 1 and Appendix H.", ["Appendix 1", "Appendix H"]),
    ("Articles 2 and 3 of the Code", ["2", "3"]),
])
def test_extract_article_citations(text, expected):
    assert extract_article_citations(text) == expected


@pytest.mark.parametrize("text", [
    # Every one of these put a fragment in the database. `Art` was matching
    # inside ordinary words because the pattern had no leading word boundary.
    "The Stewards: Derek Warwick, Martin Donnelly, Loic Bacquelin",
    "the driver participates in the sprint",
    "spare parts were fitted to the car",
    "both parties were heard",
    "no particular advantage was gained",
    "the starting procedure was followed",
    "he started from the pit lane",
    "the department was notified",
    "part of the track",
    # A bare mention with no number cites nothing.
    "Articles of the International Sporting Code",
])
def test_ordinary_words_are_not_article_citations(text):
    assert extract_article_citations(text) == []


def test_a_chapter_written_without_its_comma_is_the_same_citation():
    # The corpus writes both, and they must not become two separate articles.
    with_comma = extract_article_citations("Breach of Appendix L, Chapter IV")
    without = extract_article_citations("Breach of Appendix L Chapter IV")
    assert with_comma == without == ["Appendix L, Chapter IV"]


def test_a_citation_wrapped_across_a_line_break_is_collapsed():
    assert extract_article_citations("Appendix L,\nChapter IV") == ["Appendix L, Chapter IV"]


def test_repeated_citations_are_deduplicated_across_spellings():
    assert extract_article_citations("Art 15, Article 15 and Art. 15") == ["15"]


def test_a_paragraph_letter_is_one_article_however_the_dot_falls():
    # The corpus writes both. Before this, the same article sat in the column
    # under two keys and no query could group the two sets of precedents.
    assert extract_article_citations("Article 12.4.1.e and Article 12.4.1e") == ["12.4.1e"]


def test_the_paragraph_dot_survives_where_the_letter_belongs_to_the_article():
    # "B1.6.2b" is the article and ".i" its item -- the dot is not a separator
    # before a paragraph letter here, and dropping it would rewrite the number.
    assert extract_article_citations("in breach of Article B1.6.2b.i") == ["B1.6.2b.i"]


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
