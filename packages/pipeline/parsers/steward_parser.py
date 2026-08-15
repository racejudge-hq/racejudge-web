"""
Read the steward panel off the signature block of an FIA decision PDF.

Every stewards' decision is signed by the panel that issued it, printed as a
two-column grid on the last page immediately above the words "The Stewards":

        Tim Mayer              Matthew Selley
        Vitantonio Liuzzi      Matteo Perini
        The Stewards

The plain text layer collapses the column gap to a single space, so
"Tim Mayer Matthew Selley" is indistinguishable from one four-token name.
We therefore work from word coordinates: the two columns sit ~250pt apart,
far wider than any gap between words of the same name, so a simple x-gap
threshold splits them exactly.

Reading the grid column-major gives the panel in the order the FIA prints it,
which puts the Chairman first. That is the only positional guarantee: panels
of three, four and five are all common, and the driver steward moves around.
Driver stewards are identified by name instead — see `DRIVER_STEWARDS`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Words on one line closer than this belong to the same name; anything wider is
# the gap between the two printed columns. Measured across the corpus the
# within-name gap never exceeds ~12pt and the column gap never drops below 90pt.
COLUMN_GAP_PT = 40.0

# Rows whose baselines are within this many points are the same printed line.
ROW_TOLERANCE_PT = 3.0

_SIGNOFF_RE = re.compile(r"^\s*The\s+Stewards\s*$", re.IGNORECASE)

# A name token: capitalised, or one of the lowercase particles that appear
# inside real steward names (Loïc van der Berg, Mazen Al Hilli, ...).
_PARTICLES = {"van", "von", "de", "del", "der", "di", "da", "bin", "al", "el"}

# Boilerplate that must never be mistaken for a name. The signature block is
# preceded by the appeal-rights paragraph, so the walk upwards has to stop.
_NOT_A_NAME_RE = re.compile(
    r"\b(?:FIA|Article|Chapter|Code|Rules|Steward|Stewards|Regulations|Decision"
    r"|Reason|Competitor|Delegate|Document|Grand|Prix|Formula|Sporting|Judicial"
    r"|Disciplinary|Appeal|Penalty|Team|Manager|Race|Director|Session|Date|Car"
    r"|Driver|Time|Limits|Evidence|Guidelines"
    # Headings that sit in the left margin at the same x0 as a signature and
    # so land in the grid. "Operating Procedure" was read as a fifth panel
    # member on a 2023 decision.
    r"|Operating|Procedure|Standing|Classification|Practice|Qualifying|Sprint"
    r"|Championship|Technical|Scrutineering|Report|Notes|Annex|Appendix)\b",
    re.IGNORECASE,
)

# Panels smaller than three or larger than six are not panels — they are a lone
# delegate's sign-off, or the walk upwards has run into body text.
MIN_PANEL = 3
MAX_PANEL = 6


@dataclass(frozen=True)
class StewardPanel:
    """The panel that signed one decision."""

    chair: str
    members: tuple[str, ...]
    driver_steward: str | None = None

    def to_dict(self) -> dict:
        return {
            "chair": self.chair,
            "members": list(self.members),
            "driver_steward": self.driver_steward,
        }


def _looks_like_name(text: str) -> bool:
    """A run of words that could be one person's name."""
    parts = text.split()
    if not (1 < len(parts) <= 4):
        return False
    if _NOT_A_NAME_RE.search(text):
        return False
    for p in parts:
        if p.lower() in _PARTICLES:
            continue
        if not p[:1].isupper() or not p.replace("-", "").replace("'", "").replace("’", "").isalpha():
            return False
    return True


def _rows(words: list[dict]) -> list[list[dict]]:
    """Group words into printed lines by their baseline, left to right."""
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(w["top"] - out[-1][0]["top"]) <= ROW_TOLERANCE_PT:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def _cells(row: list[dict]) -> list[tuple[float, str]]:
    """Split one printed line into (x position, text) cells at the column gap."""
    cells: list[tuple[float, list[str]]] = []
    prev_x1: float | None = None
    for w in row:
        if prev_x1 is None or w["x0"] - prev_x1 > COLUMN_GAP_PT:
            cells.append((w["x0"], [w["text"]]))
        else:
            cells[-1][1].append(w["text"])
        prev_x1 = w["x1"]
    return [(x, " ".join(parts)) for x, parts in cells]


def parse_panel_from_words(words: list[dict]) -> StewardPanel | None:
    """
    Extract the panel from one page's words.

    `words` is pdfplumber's `page.extract_words()` output: dicts carrying
    `text`, `x0`, `x1` and `top`. Returns None when the page carries no
    signature block — technical-delegate notices and results tables do not.

    The block is not always at the foot of the page: a decision that runs to a
    second page prints its appeal-rights paragraph and signatures at the *top*
    of that page, so position on the page is never assumed.
    """
    return _panel_from_rows(_rows(words))


def _panel_from_rows(rows: list[list[dict]]) -> StewardPanel | None:
    """Find and read the signature grid in an ordered list of printed lines."""
    signoff = next(
        (i for i in range(len(rows) - 1, -1, -1)
         if _SIGNOFF_RE.match(" ".join(w["text"] for w in rows[i]))),
        None,
    )
    if signoff is None:
        return None

    # Walk upwards from the sign-off for as long as every cell reads as a name.
    grid: list[list[tuple[float, str]]] = []
    for i in range(signoff - 1, -1, -1):
        cells = _cells(rows[i])
        if not cells or not all(_looks_like_name(t) for _, t in cells):
            break
        grid.insert(0, cells)
        if len(grid) >= 4:  # the FIA never prints more than four signature rows
            break
    if not grid:
        return None

    # Column-major: down the left column first, then the right. This is the
    # order the FIA prints the panel in, so the Chairman comes out first.
    # Column boundaries come from the cells themselves rather than a fixed
    # margin, so a differently indented block still reads correctly.
    starts = sorted({round(x) for row in grid for x, _ in row})
    bounds = [starts[0]]
    for x in starts[1:]:
        if x - bounds[-1] > COLUMN_GAP_PT:
            bounds.append(x)
    columns: dict[int, list[tuple[float, str]]] = {}
    for row in grid:
        for cell in row:
            col = max(i for i, b in enumerate(bounds) if cell[0] >= b - 1)
            columns.setdefault(col, []).append(cell)
    names = [t for col in sorted(columns) for _, t in columns[col]]

    if not (MIN_PANEL <= len(names) <= MAX_PANEL):
        return None
    if len(set(names)) != len(names):  # a repeated name means we misread the grid
        return None

    return StewardPanel(
        chair=names[0],
        members=tuple(names),
        driver_steward=next((n for n in names if n in DRIVER_STEWARDS), None),
    )


def parse_panel(pdf_path: str | Path) -> StewardPanel | None:
    """
    Extract the panel from a decision PDF.

    The document is read as one continuous stream of printed lines rather than
    page by page, because the signature grid straddles the page break often
    enough to matter: the Chairman's row can sit at the foot of one page with
    the rest of the panel and the sign-off at the top of the next.
    """
    import pdfplumber

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            rows: list[list[dict]] = []
            for page in pdf.pages:
                rows.extend(_rows(page.extract_words()))
            return _panel_from_rows(rows)
    except Exception as exc:  # a corrupt or image-only PDF is not fatal
        log.warning("panel parse failed for %s: %s", pdf_path, exc)
    return None


# Former racing drivers who sit as the non-FIA member of the panel.
#
# The role cannot be read off position: a four-name grid puts the driver
# steward second in column-major order, a five-name grid puts them last, and
# the two cannot be told apart without knowing the names. This set is therefore
# derived from the corpus rather than asserted — every name below occupies the
# driver slot in more decisions than it occupies any other slot, and the nine
# most frequent occupy no other slot at all. Names that sit mostly elsewhere
# (Matthew Selley, Dennis Dean, Marcel Demers, Natalie Corsmit) are FIA
# stewards and are deliberately absent.
#
# "Tonio Luizzi" is the FIA's own misspelling of Vitantonio Liuzzi in one
# document. It is kept verbatim rather than merged, because the parser reports
# what the document says.
DRIVER_STEWARDS = frozenset({
    "Bruno Correia",
    "Danny Sullivan",
    "Derek Warwick",
    "Emanuele Pirro",
    "Enrique Bernoldi",
    "Johnny Herbert",
    "Mika Salo",
    "Pedro Lamy",
    "Tom Kristensen",
    "Tonio Luizzi",
    "Vitaly Petrov",
    "Vitantonio Liuzzi",
    "Yannick Dalmas",
})
