"""
LayoutLMv3 Structured Extraction — Phase 2, Layer 3.

Fine-tuned LayoutLMv3 for extracting structured fields from FIA decision PDFs.
Used as Layer 3 in the extraction pipeline when regex (Layer 1) and OCR (Layer 2)
yield insufficient confidence.

Architecture:
  - Base model: microsoft/layoutlmv3-base (224M params)
  - Fine-tuning: 300-doc annotated set from Phase 2 annotation campaign
  - Task: Token classification → field extraction (NER-style)
  - Training: Modal A10G GPU, ~4h for 5 epochs

Training fields (token labels):
  B-DRIVER, I-DRIVER, B-CAR_NUMBER, B-LAP, B-INFRACTION, I-INFRACTION,
  B-PENALTY, I-PENALTY, B-ARTICLE, I-ARTICLE, B-SESSION, O

Usage:
    extractor = LayoutLMExtractor()
    fields = extractor.extract(pdf_path)

    # Or use from model checkpoint:
    extractor = LayoutLMExtractor(model_path="models/layoutlm_v1")
    fields = extractor.extract(pdf_path)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "layoutlm_v1"

# Confidence threshold — below this, Layer 3 result is discarded
CONFIDENCE_THRESHOLD = 0.75


class LayoutLMExtractor:
    """
    LayoutLMv3-based field extractor for FIA decision PDFs.

    Lazy-loads the model on first call to avoid startup overhead.
    Falls back to None for each field if model is not available.
    """

    def __init__(self, model_path: str | Path | None = None):
        self._model_path = Path(model_path) if model_path else MODEL_PATH
        self._pipeline: Any = None

    def _load(self) -> bool:
        """Lazy-load the LayoutLMv3 pipeline. Returns True if successful."""
        if self._pipeline is not None:
            return True
        if not self._model_path.exists():
            log.info(
                "LayoutLMv3 model not found at %s — "
                "Layer 3 extraction disabled. "
                "Train with: python scripts/train_layoutlm.py",
                self._model_path,
            )
            return False
        try:
            from transformers import pipeline as hf_pipeline
            self._pipeline = hf_pipeline(
                "token-classification",
                model=str(self._model_path),
                aggregation_strategy="simple",
                device=-1,  # CPU; switch to 0 for GPU
            )
            log.info("LayoutLMv3 loaded from %s", self._model_path)
            return True
        except ImportError:
            log.warning(
                "transformers not installed — LayoutLMv3 unavailable. "
                "pip install transformers torch"
            )
            return False
        except Exception as exc:
            log.error("LayoutLMv3 load failed: %s", exc)
            return False

    def extract(self, pdf_path: str | Path) -> dict[str, Any]:
        """
        Extract structured fields from a PDF using LayoutLMv3.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            Dict with extracted fields. Values are None if not found or
            confidence below threshold. Empty dict if model unavailable.
        """
        if not self._load():
            return {}

        path = Path(pdf_path)
        if not path.exists():
            log.warning("LayoutLMv3: PDF not found: %s", path)
            return {}

        try:
            from pdf2image import convert_from_path
        except ImportError:
            log.warning("pdf2image not installed — LayoutLMv3 needs rendered pages")
            return {}

        try:
            pages = convert_from_path(str(path), dpi=150, first_page=1, last_page=3)
        except Exception as exc:
            log.error("LayoutLMv3 PDF render failed: %s", exc)
            return {}

        # Run inference on first 3 pages (decision content is usually there)
        all_entities: list[dict] = []
        for page_img in pages:
            try:
                entities = self._pipeline(page_img)  # type: ignore[misc]
                all_entities.extend(entities or [])
            except Exception as exc:
                log.warning("LayoutLMv3 inference failed on page: %s", exc)

        return self._aggregate_entities(all_entities)

    def _aggregate_entities(self, entities: list[dict]) -> dict[str, Any]:
        """Aggregate NER entities into structured field dict."""
        fields: dict[str, list[str]] = {}
        for ent in entities:
            score = ent.get("score", 0)
            if score < CONFIDENCE_THRESHOLD:
                continue
            label = ent.get("entity_group", ent.get("entity", "")).replace("B-", "").replace("I-", "")
            word  = ent.get("word", "").strip()
            if label and word:
                fields.setdefault(label, []).append(word)

        def _first(key: str) -> str | None:
            vals = fields.get(key, [])
            return vals[0] if vals else None

        def _join(key: str) -> str | None:
            vals = fields.get(key, [])
            return " ".join(vals) if vals else None

        return {
            "driver_name":       _first("DRIVER"),
            "car_number":        _parse_int(_first("CAR_NUMBER")),
            "lap_number":        _parse_int(_first("LAP")),
            "infraction_type":   _join("INFRACTION"),
            "outcome":           _join("PENALTY"),
            "article_cited":     fields.get("ARTICLE", []),
            "session_type":      _first("SESSION"),
            "_source":           "layoutlmv3",
        }

    def is_available(self) -> bool:
        """Returns True if model is loaded and ready."""
        return self._pipeline is not None or self._load()


def _parse_int(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(re.sub(r"[^0-9]", "", val))
    except (ValueError, TypeError):
        return None


import re  # noqa: E402 (needed by _parse_int above)
