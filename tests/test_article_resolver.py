"""Tests for article_resolver.py"""

import pytest

from packages.pipeline.resolvers.article_resolver import ArticleCitation, ArticleResolver


@pytest.fixture
def r():
    return ArticleResolver()


# ---------------------------------------------------------------------------
# Extraction tests
# ---------------------------------------------------------------------------

def test_extract_basic_article(r):
    citations = r.extract("pursuant to Art. 48.1 of the Sporting Regulations")
    assert len(citations) == 1
    assert citations[0].article_number == "48.1"


def test_extract_article_full_word(r):
    citations = r.extract("in breach of Article 2.3 of the ISC")
    assert any(c.article_number == "2.3" for c in citations)


def test_extract_document_hint_sporting(r):
    citations = r.extract("Art. 33.3 of the Sporting Regulations")
    assert citations[0].document_name == "F1 Sporting Regulations"


def test_extract_document_hint_penalty_guidelines(r):
    citations = r.extract("as per Art. 38.1 of the Penalty Guidelines")
    assert citations[0].document_name == "FIA Penalty Guidelines"


def test_extract_document_hint_isc(r):
    citations = r.extract("Article 12.1 of the International Sporting Code")
    assert citations[0].document_name == "ISC"


def test_extract_appendix(r):
    citations = r.extract("Appendix L Chapter 4 of the Regulations")
    assert any("Appendix L" in c.article_number for c in citations)


def test_extract_appendix_no_chapter(r):
    citations = r.extract("violating Appendix H of the Technical Regulations")
    assert any("Appendix H" in c.article_number for c in citations)


def test_extract_multiple_articles(r):
    text = "Art. 48.1 and Art. 55.13 of the Sporting Regulations"
    citations = r.extract(text)
    nums = [c.article_number for c in citations]
    assert "48.1" in nums
    assert "55.13" in nums


def test_extract_deduplication(r):
    text = "Art. 48.1 and again Art. 48.1 was cited"
    citations = r.extract(text)
    nums = [c.article_number for c in citations]
    assert nums.count("48.1") == 1


def test_extract_strings_convenience(r):
    text = "Art. 48.1 and Art. 20.5"
    nums = r.extract_strings(text)
    assert "48.1" in nums
    assert "20.5" in nums


def test_extract_empty_text(r):
    assert r.extract("") == []


def test_extract_no_articles(r):
    assert r.extract("The stewards met and decided on the matter.") == []


def test_known_article_doc_map(r):
    citations = r.extract("Art. 38.1 was applied")
    assert citations[0].document_name == "FIA Penalty Guidelines"


def test_article_citation_to_dict(r):
    c = ArticleCitation("48.1", "F1 Sporting Regulations", "Art. 48.1", None)
    d = c.to_dict()
    assert d["article_number"] == "48.1"
    assert d["document_name"] == "F1 Sporting Regulations"
    assert d["article_id"] is None
