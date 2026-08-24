"""
Incident Extractor — Phase 2, 3-layer pipeline.

Layer 1: pdfplumber text + regex (decision_parser.py)
Layer 2: Tesseract OCR + regex            (tesseract_fallback.py)
Layer 3: LayoutLMv3 fine-tuned            (layoutlm_extractor.py)

Confidence scoring:
  - Layer 1 wins if char_count >= 100 AND regex extracts >= 3 fields
  - Layer 2 wins if OCR yields >= 100 chars AND regex >= 3 fields
  - Layer 3 supplements missing fields (never fully overrides L1/L2)
  - Fields merged with priority: L1 > L2 > L3 (first non-None wins)

Output: ExtractionResult with all structured fields + confidence metadata.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    doc_id:              str
    driver_name:         str | None = None
    car_number:          int | None = None
    infraction_type:     str | None = None
    infraction_category: str | None = None  # normalised FIA taxonomy
    outcome:             str | None = None
    penalty_type:        str | None = None  # NFA/REP/5s/10s/DT/GRID/DSQ
    penalty_seconds:     int | None = None
    penalty_points:      int = 0
    # "full" / "partial" / None — a penalty imposed but not enforced unless the
    # party reoffends. Kept apart from penalty_type, which records what was
    # imposed; this records whether any of it was actually served.
    penalty_suspended:   str | None = None
    grid_positions:      int | None = None
    lap_number:          int | None = None
    session_type:        str | None = None
    corner:              str | None = None
    contact:             bool | None = None
    # The vision evidence the stewards state they reviewed. Not URLs — no
    # decision document in the corpus contains one. See extract_video_refs.
    video_refs:          list[str] | None = None
    article_cited:       list[str] = field(default_factory=list)
    reasoning_text:      str = ""
    drivers:             list[dict] = field(default_factory=list)
    # The other cars in the incident — impeded, hit, or forced off. Held apart
    # from `drivers` because they are not what this document rules on.
    involved_drivers:    list[dict] = field(default_factory=list)
    extractor_version:   str = "v1.0-regex"
    confidence:          float = 0.0
    layer_used:          int = 1
    raw_text:            str = ""

    def to_dict(self) -> dict:
        return {
            "doc_id":              self.doc_id,
            "driver_name":         self.driver_name,
            "car_number":          self.car_number,
            "infraction_type":     self.infraction_type,
            "infraction_category": self.infraction_category,
            "outcome":             self.outcome,
            "penalty_type":        self.penalty_type,
            "penalty_seconds":     self.penalty_seconds,
            "penalty_points":      self.penalty_points,
            "penalty_suspended":   self.penalty_suspended,
            "grid_positions":      self.grid_positions,
            "lap_number":          self.lap_number,
            "session_type":        self.session_type,
            "corner":              self.corner,
            "contact":             self.contact,
            "video_refs":          self.video_refs,
            "article_cited":       self.article_cited,
            "reasoning_text":      self.reasoning_text,
            "drivers":             self.drivers,
            "involved_drivers":    self.involved_drivers,
            "extractor_version":   self.extractor_version,
        }


# ---------------------------------------------------------------------------
# FIA infraction category taxonomy (from 2025 Penalty Guidelines)
# ---------------------------------------------------------------------------

# Keys are matched as substrings against a lowercased infraction_type, first
# match wins — so order is most-specific-first, and every label produced by
# _INFRACTION_PATTERNS in decision_parser.py must have a key here. Labels
# without one extract a type but still store a NULL category, which is what
# left "false start", "starting procedure", "leaving the track", "driving
# unnecessarily slowly" and "media commitment breach" unclassified: the key
# "start procedure" never matches the label "starting procedure".
_INFRACTION_CATEGORY_MAP: dict[str, str] = {
    # --- Contact and racing conduct ---
    "causing a collision":                          "collision",
    "forcing another driver off the track":         "forcing_off_track",
    "dangerous driving":                            "dangerous_driving",
    "weaving":                                      "erratic_driving",
    "driving unnecessarily slowly":                 "driving_slowly",
    "crossing the track":                           "crossing_track",

    # --- Track limits (incl. the delete-the-lap-time form) ---
    "deleted lap times":                            "track_limits",
    "gaining an advantage off track":               "track_limits",
    "leaving the track":                            "track_limits",
    "track limits":                                 "track_limits",

    # --- Pit lane. Speeding before the generic pit-lane key. ---
    "pit lane speeding":                            "pit_lane_speed",
    "released in an unsafe condition":              "unsafe_release",
    "unsafe release":                               "unsafe_release",
    "pit lane infringement":                        "pit_lane",

    # --- Flags and neutralisations ---
    "ignoring blue flags":                          "blue_flag",
    "yellow flag violation":                        "yellow_flag",
    "safety car line time limit":                   "safety_car_line_time",
    "failing to maintain distance":                 "safety_car",
    "overtaking under safety car":                  "safety_car",
    "safety car violation":                         "safety_car",
    "vsc infringement":                             "vsc",

    # --- Starts and procedure ---
    "false start":                                  "false_start",
    "practice start infringement":                  "practice_start",
    "starting procedure":                           "start_procedure",
    "start procedure":                              "start_procedure",
    "formation lap":                                "formation_lap",

    # --- Sporting regulations ---
    "impeding":                                     "impeding",
    "107% rule":                                    "107_percent",
    "failure to follow race director instructions": "race_director_instructions",

    # --- Technical and scrutineering ---
    "parc ferme breach":                            "parc_ferme",
    "power unit element infringement":              "technical",
    "technical infringement":                       "technical",
    "weighing procedure":                           "weighing",

    # --- Off-track obligations and administrative outcomes ---
    "driver obligation breach":                     "driver_obligation",
    "media commitment breach":                      "driver_obligation",
    "disqualification":                             "disqualification",
    "reprimand":                                    "administrative",
    "fine":                                         "administrative",
}

_PENALTY_TYPE_MAP: dict[str, str] = {
    "no further action":    "NFA",
    "nfa":                  "NFA",
    "reprimand":            "REP",
    "5 second":             "5s",
    "5s":                   "5s",
    "10 second":            "10s",
    "10s":                  "10s",
    "stop-and-go":          "SG",
    "stop and go":          "SG",
    "drive-through":        "DT",
    "drive through":        "DT",
    "pit lane penalty":     "DT",
    "grid penalty":         "GRID",
    "grid position":        "GRID",
    "disqualif":            "DSQ",
    # The stewards issue warnings and fines as standalone outcomes; neither had
    # a penalty_type, so those rulings stored NULL despite a clear decision.
    "warning":              "WARN",
    "fine":                 "FINE",
    # A pit lane start is its own penalty, not a grid drop. It is the standard
    # sanction for a parc fermé breach or an out-of-allocation power unit.
    "pit lane start":       "PIT",
}

# Time penalties are resolved numerically, before the substring map. The map
# alone was wrong in two ways: it knew only 5s and 10s, so the 15s/20s/30s
# penalties the FIA also issues fell through to NULL; and because its keys are
# matched as substrings, "5 second" matched inside "15 second penalty" and a
# 15-second penalty was silently recorded as a 5-second one.
_SECONDS_PENALTY_RE = re.compile(r"\b(\d{1,2})\s*(?:s\b|second)", re.IGNORECASE)


def _normalise_penalty_type(outcome: str | None) -> str | None:
    if not outcome:
        return None
    lower = outcome.lower()
    m = _SECONDS_PENALTY_RE.search(lower)
    if m and "penalty" in lower:
        return f"{int(m.group(1))}s"
    for key, val in _PENALTY_TYPE_MAP.items():
        if key in lower:
            return val
    return None


def _normalise_infraction_category(infraction: str | None) -> str | None:
    if not infraction:
        return None
    lower = infraction.lower()
    for key, val in _INFRACTION_CATEGORY_MAP.items():
        if key in lower:
            return val
    return None


def _extract_reasoning(text: str) -> str:
    """Extract the stewards' reasoning section from raw text."""
    from packages.pipeline.parsers.decision_parser import extract_reason

    return extract_reason(text)


def _subject_numbers(cleaned: str, car_number: int | None) -> set[int]:
    """Every car this document rules on, for excluding from the counterparties.

    The header list and the single-car fallback can disagree — the fallback also
    reads the title, which is sometimes a neighbouring document's — so both are
    excluded. Over-excluding costs at most one counterparty; under-excluding
    files the accused driver as their own victim.
    """
    from packages.pipeline.parsers.decision_parser import extract_subjects

    numbers = {n for n, _ in extract_subjects(cleaned)}
    if car_number is not None:
        numbers.add(car_number)
    return numbers


def _field_count(d: dict) -> int:
    """Count how many fields are non-None."""
    key_fields = ["driver_name", "car_number", "infraction_type", "outcome",
                  "lap_number", "session_type", "penalty_points"]
    return sum(1 for k in key_fields if d.get(k) is not None)


def _merge(primary: dict, secondary: dict) -> dict:
    """Merge two extraction dicts: primary wins on non-None values."""
    merged = dict(secondary)
    for k, v in primary.items():
        if v is not None and v != [] and v != "":
            merged[k] = v
    return merged


# ---------------------------------------------------------------------------
# 3-Layer extractor
# ---------------------------------------------------------------------------

class IncidentExtractor:
    """
    3-layer FIA decision incident extractor.

    Usage:
        extractor = IncidentExtractor()
        result = extractor.extract(record)   # record from decisions.jsonl
        result = extractor.extract_from_pdf(pdf_path, doc_id, season)
    """

    def __init__(self, enable_layoutlm: bool = True):
        self._layoutlm = None
        self._enable_layoutlm = enable_layoutlm
        from packages.pipeline.resolvers.article_resolver import ArticleResolver
        from packages.pipeline.resolvers.driver_resolver import DriverResolver
        self._driver_resolver  = DriverResolver()
        self._article_resolver = ArticleResolver()

    def _get_layoutlm(self):
        if not self._enable_layoutlm:
            return None
        if self._layoutlm is None:
            from packages.pipeline.parsers.layoutlm_extractor import LayoutLMExtractor
            self._layoutlm = LayoutLMExtractor()
        return self._layoutlm

    # ------------------------------------------------------------------
    # Layer 1: regex over existing raw_text
    # ------------------------------------------------------------------

    def _layer1(self, record: dict) -> dict:
        from packages.pipeline.parsers.decision_parser import (
            extract_car_number,
            extract_contact,
            extract_driver_name,
            extract_grid_positions,
            extract_infraction_type,
            extract_involved_cars,
            extract_lap_number,
            extract_outcome,
            extract_penalty_points,
            extract_session_type,
            extract_subjects,
            extract_suspension,
            extract_table_subjects,
            extract_turn_number,
            extract_video_refs,
        )
        from packages.pipeline.parsers.text_cleaner import (
            clean_decision_text,
            extract_article_citations,
        )

        text = record.get("raw_text", "")
        cleaned = clean_decision_text(text)

        # decision_parser.extract_incident() classifies against "{title}\n{text}",
        # and the FIA title is often the only place the offence is named at all
        # ("Deleted Lap Times", "Parc Fermé", "Forcing Another Driver Off Track").
        # This layer used to pass the body alone, so those rulings extracted no
        # infraction_type. Match the parser's contract: title-aware for the
        # document-level fields, body-only for the per-incident ones, since a
        # title never carries a lap number and rarely a driver name.
        title = record.get("title") or ""
        combined = f"{title}\n{cleaned}" if title else cleaned

        car_number = extract_car_number(combined)
        return {
            "raw_text":        cleaned,
            "car_number":      car_number,
            "driver_name":     extract_driver_name(cleaned),
            "subjects":        extract_subjects(cleaned),
            "table_subjects":  extract_table_subjects(cleaned),
            "involved_cars":   extract_involved_cars(cleaned, _subject_numbers(cleaned, car_number)),
            "infraction_type": extract_infraction_type(combined),
            "outcome":         extract_outcome(combined),
            # Read from the body: the Decision section states it, titles never do.
            "suspended":       extract_suspension(cleaned),
            "grid_positions":  extract_grid_positions(cleaned),
            "penalty_points":  extract_penalty_points(combined) or 0,
            "lap_number":      extract_lap_number(cleaned),
            "session_type":    extract_session_type(combined),
            "corner":          extract_turn_number(cleaned),
            "contact":         extract_contact(cleaned),
            "video_refs":      extract_video_refs(cleaned),
            "article_cited":   extract_article_citations(cleaned),
            "reasoning_text":  _extract_reasoning(cleaned),
        }

    # ------------------------------------------------------------------
    # Layer 2: OCR fallback
    # ------------------------------------------------------------------

    def _layer2(self, pdf_path: str | Path) -> dict:
        from packages.pipeline.parsers.decision_parser import (
            extract_car_number,
            extract_contact,
            extract_driver_name,
            extract_grid_positions,
            extract_infraction_type,
            extract_involved_cars,
            extract_lap_number,
            extract_outcome,
            extract_penalty_points,
            extract_session_type,
            extract_subjects,
            extract_suspension,
            extract_table_subjects,
            extract_turn_number,
            extract_video_refs,
        )
        from packages.pipeline.parsers.tesseract_fallback import ocr_pdf
        from packages.pipeline.parsers.text_cleaner import (
            clean_decision_text,
            extract_article_citations,
        )

        try:
            text = ocr_pdf(pdf_path)
        except Exception as exc:
            log.warning("OCR failed: %s", exc)
            return {}

        cleaned = clean_decision_text(text)
        car_number = extract_car_number(cleaned)
        return {
            "raw_text":        cleaned,
            "car_number":      car_number,
            "driver_name":     extract_driver_name(cleaned),
            "subjects":        extract_subjects(cleaned),
            "table_subjects":  extract_table_subjects(cleaned),
            "involved_cars":   extract_involved_cars(cleaned, _subject_numbers(cleaned, car_number)),
            "infraction_type": extract_infraction_type(cleaned),
            "outcome":         extract_outcome(cleaned),
            "suspended":       extract_suspension(cleaned),
            "grid_positions":  extract_grid_positions(cleaned),
            "penalty_points":  extract_penalty_points(cleaned) or 0,
            "lap_number":      extract_lap_number(cleaned),
            "session_type":    extract_session_type(cleaned),
            "corner":          extract_turn_number(cleaned),
            "contact":         extract_contact(cleaned),
            "video_refs":      extract_video_refs(cleaned),
            "article_cited":   extract_article_citations(cleaned),
            "reasoning_text":  _extract_reasoning(cleaned),
        }

    # ------------------------------------------------------------------
    # Layer 3: LayoutLMv3
    # ------------------------------------------------------------------

    def _layer3(self, pdf_path: str | Path) -> dict:
        llm = self._get_layoutlm()
        if llm is None or not llm.is_available():
            return {}
        try:
            return llm.extract(pdf_path)
        except Exception as exc:
            log.warning("LayoutLMv3 extraction failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Resolve drivers + articles
    # ------------------------------------------------------------------

    def _driver_entry(
        self, name: str | None, number: int | None, season: int | None
    ) -> dict | None:
        rec = self._driver_resolver.resolve(name=name, number=number, season=season)
        if rec:
            return {
                "code":      rec.get("code"),
                "full_name": rec.get("full_name"),
                "number":    number or rec.get("number"),
            }
        # Fallback: use extracted name/number as-is
        if name or number is not None:
            return {"code": None, "full_name": name, "number": number}
        return None

    def _resolve_drivers(self, fields: dict, season: int | None) -> list[dict]:
        # The header list carries every driver a joint summons is issued to; the
        # single-car fields are the fallback for the documents that have no
        # header, and they reproduce the first header entry when there is one.
        subjects: list[tuple[int | None, str | None]] = [
            (n, nm) for n, nm in (fields.get("subjects") or [])
        ]
        # Tabular rulings — deleted lap times, safety car delta breaches — name
        # their drivers in a table instead, and have no subject header at all.
        # 152 of them were stored against nobody, so the laps the stewards
        # deleted were missing from every one of those drivers' records.
        if not subjects:
            subjects = [(n, nm) for n, nm in (fields.get("table_subjects") or [])]
        if not subjects:
            subjects = [(fields.get("car_number"), fields.get("driver_name"))]
        resolved = [self._driver_entry(nm, n, season) for n, nm in subjects]
        return [d for d in resolved if d]

    def _resolve_involved(self, fields: dict, season: int | None) -> list[dict]:
        """Resolve the counterparty car numbers. Names are never stated for these."""
        out: list[dict] = []
        for number in fields.get("involved_cars") or []:
            rec = self._driver_resolver.resolve_number(number, season)
            out.append({
                "code":      rec.get("code") if rec else None,
                "full_name": rec.get("full_name") if rec else None,
                "number":    number,
            })
        return out

    # ------------------------------------------------------------------
    # Main extract
    # ------------------------------------------------------------------

    def extract(self, record: dict, pdf_path: str | Path | None = None) -> ExtractionResult:
        """
        Extract structured incident fields from a parsed decision record.

        Args:
            record:   Dict from decisions.jsonl (must have raw_text, doc_id, season).
            pdf_path: Optional path to PDF for Layer 2/3 fallback.
        """
        doc_id  = record.get("doc_id", "unknown")
        season  = record.get("season")
        char_cnt = len(record.get("raw_text", ""))

        # Layer 1
        l1 = self._layer1(record)
        layer_used = 1
        confidence = min(1.0, _field_count(l1) / 5.0)

        # Layer 2 — only if char_count < 100 or fewer than 2 fields found
        l2: dict = {}
        if (char_cnt < 100 or _field_count(l1) < 2) and pdf_path:
            log.info("Layer 2 OCR for doc_id=%s (char_count=%d)", doc_id, char_cnt)
            l2 = self._layer2(pdf_path)
            if _field_count(l2) > _field_count(l1):
                layer_used = 2
                confidence = min(1.0, _field_count(l2) / 5.0)

        # Layer 3 — supplement missing fields
        l3: dict = {}
        best = _merge(l1, l2) if l2 else l1
        if _field_count(best) < 3 and pdf_path:
            l3 = self._layer3(pdf_path)
            if l3:
                if layer_used < 3:
                    layer_used = 3
                best = _merge(best, l3)
                confidence = min(1.0, _field_count(best) / 5.0 + 0.1)

        # Resolve drivers
        drivers  = self._resolve_drivers(best, season)
        involved = self._resolve_involved(best, season)

        # Resolve articles — normalize raw text to article numbers only
        articles_raw = best.get("article_cited", [])
        if isinstance(articles_raw, str):
            articles_raw = [articles_raw]
        # Normalize: "Art. 48.1" → "48.1", "Appendix L Ch.4" stays as-is
        # Drop what normalises to nothing -- text carrying no article number.
        articles_raw = [n for a in articles_raw if a and (n := _normalize_article(a))]
        articles_raw = list(dict.fromkeys(articles_raw))  # dedup, preserve order

        return ExtractionResult(
            doc_id              = doc_id,
            driver_name         = best.get("driver_name"),
            car_number          = best.get("car_number"),
            infraction_type     = best.get("infraction_type"),
            infraction_category = _normalise_infraction_category(best.get("infraction_type")),
            outcome             = best.get("outcome"),
            penalty_type        = _normalise_penalty_type(best.get("outcome")),
            penalty_seconds     = _parse_penalty_seconds(best.get("outcome")),
            penalty_points      = best.get("penalty_points") or 0,
            penalty_suspended   = best.get("suspended"),
            grid_positions      = best.get("grid_positions"),
            lap_number          = best.get("lap_number"),
            session_type        = best.get("session_type"),
            corner              = best.get("corner"),
            # The Fact section when the layer read one; the category label only
            # as a last resort, because the label is applied after the fact and
            # disagrees with the document in both directions. See extract_contact.
            contact             = (best["contact"] if best.get("contact") is not None
                                   else _infer_contact(best.get("infraction_type"))),
            video_refs          = best.get("video_refs"),
            article_cited       = articles_raw,
            reasoning_text      = best.get("reasoning_text", ""),
            drivers             = drivers,
            involved_drivers    = involved,
            extractor_version   = f"v2.0-layer{layer_used}",
            confidence          = confidence,
            layer_used          = layer_used,
            raw_text            = best.get("raw_text", record.get("raw_text", "")),
        )

    def extract_from_pdf(
        self,
        pdf_path: str | Path,
        doc_id: str,
        season: int | None = None,
    ) -> ExtractionResult:
        """Extract from a PDF file directly (no pre-parsed record)."""
        import pdfplumber
        path = Path(pdf_path)
        raw_text = ""
        try:
            with pdfplumber.open(str(path)) as pdf:
                raw_text = "\n".join(
                    (p.extract_text() or "") for p in pdf.pages
                ).strip()
        except Exception as exc:
            log.warning("pdfplumber failed on %s: %s", path.name, exc)

        record = {
            "doc_id":   doc_id,
            "season":   season or 0,
            "raw_text": raw_text,
            "char_count": len(raw_text),
        }
        return self.extract(record, pdf_path=path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_article(raw: str) -> str:
    """Strip an 'Art.'/'Article' prefix, leaving the article number.

    `extract_article_citations` now returns references already in this form, so
    this is a no-op on its output. It stays for the callers that still hand
    over raw matched text.

    What it no longer does is return the input unchanged when it finds no
    article number. That fallback is the reason `artin` -- the tail of steward
    *Martin*'s name -- was stored as a cited article 402 times: the prefix
    regex matched inside the word, and anything the number regex then failed
    to parse was passed straight through to the database. Text with no article
    number in it cites no article, and now returns empty for the caller to drop.
    """
    import re
    raw = " ".join(raw.split())
    if re.match(r"^Appendix\b", raw, re.IGNORECASE):
        return raw
    m = re.match(
        r"^art(?:icle)?s?\.?\s*([A-Z]?\d+(?:\.[0-9A-Za-z]+)*(?:[a-z](?![a-z]))?)$",
        raw,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).rstrip(".")
    return raw if any(ch.isdigit() for ch in raw) else ""


def _parse_penalty_seconds(outcome: str | None) -> int | None:
    if not outcome:
        return None
    import re
    # Match "5 second", "10s", "5s time" etc.
    m = re.search(r"(\d+)\s*s(?:econd)?", outcome, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _infer_contact(infraction: str | None) -> bool | None:
    """Last-resort guess from the infraction label, used only when the document
    states no Fact section. "collision" was matched as a literal substring, so
    the label "collided" — the word the FIA actually writes — did not count."""
    if not infraction:
        return None
    contact_keywords = ["collid", "collision", "contact", "hit", "crash", "impact"]
    lower = infraction.lower()
    return any(kw in lower for kw in contact_keywords)
