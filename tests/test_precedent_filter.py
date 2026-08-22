"""The precedent corpus filter — which documents may be returned as precedent.

The FIA publishes its paperwork through the same feed as its rulings, so the
retrieval layer has to decide what counts. The filter is easy to get wrong in
the direction that silently loses real precedent, which is why it is pinned
here rather than left to the query text.
"""

from apps.api.retrieval.semantic_search import _DECIDES_SOMETHING


def test_both_retrieval_legs_apply_the_same_filter():
    """A hybrid search is only as clean as its dirtiest branch."""
    from pathlib import Path
    bm25 = Path("apps/api/retrieval/bm25_search.py").read_text()
    assert _DECIDES_SOMETHING in bm25


def test_the_filter_keeps_a_ruling_that_has_a_penalty_but_no_category():
    """249 real rulings have no taxonomy label but a real penalty.

    134 are No Further Action — an NFA on a Turn 2 incident is precedent of
    exactly the kind a steward searches for. Filtering on
    `infraction_category IS NULL` alone would discard every one of them.
    """
    assert _evaluate(_DECIDES_SOMETHING, category=None, penalty="NFA") is True
    assert _evaluate(_DECIDES_SOMETHING, category=None, penalty="DSQ") is True


def test_the_filter_keeps_a_ruling_that_has_a_category_but_no_penalty():
    assert _evaluate(_DECIDES_SOMETHING, category="causing_a_collision",
                     penalty=None) is True


def test_the_filter_drops_paperwork_that_decides_neither():
    """Stewards Bulletins, Substitutions, "Formation of the Grid", summonses."""
    assert _evaluate(_DECIDES_SOMETHING, category=None, penalty=None) is False


def _evaluate(sql: str, *, category, penalty) -> bool:
    """Evaluate the SQL predicate's three-valued logic in Python.

    The predicate is pure `IS NOT NULL` / `OR`, so it carries over exactly.
    """
    expr = (sql.replace("i.infraction_category IS NOT NULL",
                        repr(category is not None))
               .replace("i.penalty_type IS NOT NULL", repr(penalty is not None))
               .replace(" OR ", " or "))
    return bool(eval(expr))  # noqa: S307 — a fixed literal expression
