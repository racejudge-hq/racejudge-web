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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    grid_positions:      int | None = None
    lap_number:          int | None = None
    session_type:        str | None = None
    corner:              str | None = None
    contact:             bool | None = None
    article_cited:       list[str] = field(default_factory=list)
    reasoning_text:      str = ""
    drivers:             list[dict] = field(default_factory=list)
    extractor_version:   str = "v1.0-regex"
    confidence:          float = 0.0
    layer_used:          int = 1
    raw_text:            str = ""

    def to_dict(self) -> dict:
        d = {
            "doc_id":              self.doc_id,
            "driver_name":         self.driver_name,
            "car_number":          self.car_number,
            "infraction_type":     self.infraction_type,
            "infraction_category": self.infraction_category,
            "outcome":             self.outcome,
            "penalty_type":        self.penalty_type,
            "penalty_seconds":     self.penalty_seconds,
            "penalty_points":      self.penalty_points,
            "grid_positions":      self.grid_positions,
            "lap_number":          self.lap_number,
            "session_type":        self.session_type,
            "corner":              self.corner,
            "contact":             self.contact,
            "article_cited":       self.article_cited,
            "reasoning_text":      self.reasoning_text,
            "drivers":             self.drivers,
            "extractor_version":   self.extractor_version,
        }
        return d


# ---------------------------------------------------------------------------
# FIA infraction category taxonomy (from 2025 Penalty Guidelines)
# ---------------------------------------------------------------------------

_INFRACTION_CATEGORY_MAP: dict[str, str] = {
    "causing a collision":    "collision",
    "track limits":           "track_limits",
    "unsafe release":         "unsafe_release",
    "pit lane speeding":      "pit_lane_speed",
    "impeding":               "impeding",
    "ignoring blue flags":    "blue_flag",
    "safety car violation":   "safety_car",
    "vsc infringement":       "vsc",
    "yellow flag violation":  "yellow_flag",
    "disqualification":       "disqualification",
    "weaving":                "erratic_driving",
    "dangerous driving":      "dangerous_driving",
    "formation lap":          "formation_lap",
    "start procedure":        "start_procedure",
    "technical infringement": "technical",
    "reprimand":              "administrative",
    "fine":                   "administrative",
}

_PENALTY_TYPE_MAP: dict[str, str] = {
    "no further action":    "NFA",
    "nfa":                  "NFA",
    "reprimand":            "REP",
    "5 second":             "5s",
    "5s":                   "5s",
    "10 second":            "10s",
    "10s":                  "10s",
    "drive-through":        "DT",
    "drive through":        "DT",
    "pit lane penalty":     "DT",
    "grid penalty":         "GRID",
    "grid position":        "GRID",
    "disqualif":            "DSQ",
}


def _normalise_penalty_type(outcome: str | None) -> str | None:
    if not outcome:
        return None
    lower = outcome.lower()
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
    lower = text.lower()
    markers = [
        "having considered",
        "the stewards",
        "decision:",
        "the competitors were",
        "after hearing",
    ]
    for marker in markers:
        idx = lower.find(marker)
        if idx != -1:
            return text[idx: idx + 2000].strip()
    return text[:2000].strip()


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
        from packages.pipeline.resolvers.driver_resolver import DriverResolver
        from packages.pipeline.resolvers.article_resolver import ArticleResolver
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
            extract_driver_name,
            extract_infraction_type,
            extract_lap_number,
            extract_outcome,
            extract_penalty_points,
            extract_session_type,
            extract_turn_number,
        )
        from packages.pipeline.parsers.text_cleaner import (
            clean_decision_text,
            extract_article_citations,
        )

        text = record.get("raw_text", "")
        cleaned = clean_decision_text(text)

        return {
            "raw_text":        cleaned,
            "car_number":      extract_car_number(cleaned),
            "driver_name":     extract_driver_name(cleaned),
            "infraction_type": extract_infraction_type(cleaned),
            "outcome":         extract_outcome(cleaned),
            "penalty_points":  extract_penalty_points(cleaned) or 0,
            "lap_number":      extract_lap_number(cleaned),
            "session_type":    extract_session_type(cleaned),
            "corner":          extract_turn_number(cleaned),
            "article_cited":   extract_article_citations(cleaned),
            "reasoning_text":  _extract_reasoning(cleaned),
        }

    # ------------------------------------------------------------------
    # Layer 2: OCR fallback
    # ------------------------------------------------------------------

    def _layer2(self, pdf_path: str | Path) -> dict:
        from packages.pipeline.parsers.tesseract_fallback import ocr_pdf
        from packages.pipeline.parsers.decision_parser import (
            extract_car_number, extract_driver_name, extract_infraction_type,
            extract_lap_number, extract_outcome, extract_penalty_points,
            extract_session_type, extract_turn_number,
        )
        from packages.pipeline.parsers.text_cleaner import (
            clean_decision_text, extract_article_citations,
        )

        try:
            text = ocr_pdf(pdf_path)
        except Exception as exc:
            log.warning("OCR failed: %s", exc)
            return {}

        cleaned = clean_decision_text(text)
        return {
            "raw_text":        cleaned,
            "car_number":      extract_car_number(cleaned),
            "driver_name":     extract_driver_name(cleaned),
            "infraction_type": extract_infraction_type(cleaned),
            "outcome":         extract_outcome(cleaned),
            "penalty_points":  extract_penalty_points(cleaned) or 0,
            "lap_number":      extract_lap_number(cleaned),
            "session_type":    extract_session_type(cleaned),
            "corner":          extract_turn_number(cleaned),
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

    def _resolve_drivers(self, fields: dict, season: int | None) -> list[dict]:
        name   = fields.get("driver_name")
        number = fields.get("car_number")
        rec    = self._driver_resolver.resolve(name=name, number=number, season=season)
        if rec:
            return [{
                "code":      rec.get("code"),
                "full_name": rec.get("full_name"),
                "number":    number or rec.get("number"),
            }]
        # Fallback: use extracted name/number as-is
        if name or number is not None:
            return [{"code": None, "full_name": name, "number": number}]
        return []

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
        drivers = self._resolve_drivers(best, season)

        # Resolve articles — normalize raw text to article numbers only
        articles_raw = best.get("article_cited", [])
        if isinstance(articles_raw, str):
            articles_raw = [articles_raw]
        # Normalize: "Art. 48.1" → "48.1", "Appendix L Ch.4" stays as-is
        articles_raw = [_normalize_article(a) for a in articles_raw if a]
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
            lap_number          = best.get("lap_number"),
            session_type        = best.get("session_type"),
            corner              = best.get("corner"),
            contact             = _infer_contact(best.get("infraction_type")),
            article_cited       = articles_raw,
            reasoning_text      = best.get("reasoning_text", ""),
            drivers             = drivers,
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
    """Strip 'Art.' / 'Article' prefix, return just the number or 'Appendix X' form."""
    import re
    raw = raw.strip()
    m = re.match(r"art(?:icle)?\.?\s*(\d[\d.]*)", raw, re.IGNORECASE)
    if m:
        return m.group(1)
    return raw


def _parse_penalty_seconds(outcome: str | None) -> int | None:
    if not outcome:
        return None
    import re
    # Match "5 second", "10s", "5s time" etc.
    m = re.search(r"(\d+)\s*s(?:econd)?", outcome, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _infer_contact(infraction: str | None) -> bool | None:
    if not infraction:
        return None
    contact_keywords = ["collision", "contact", "hit", "crash", "impact"]
    lower = infraction.lower()
    return any(kw in lower for kw in contact_keywords)
