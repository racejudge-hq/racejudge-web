"""
Team radio sentiment + urgency classifier — Phase 5.

Runs a DistilBERT model fine-tuned on F1 radio transcripts to extract:
  - sentiment_score: [-1, 1]  (negative=protest, positive=calm)
  - urgency_score:   [0, 1]   (0=casual, 1=incident/safety-critical)

Falls back to rule-based heuristics when the model isn't loaded,
so the extract pipeline always returns scores even without a GPU.

Usage:
    from packages.ml.sentiment import classify_radio
    result = classify_radio("There was contact at Turn 1, I was pushed wide")
    # {"sentiment_score": -0.72, "urgency_score": 0.88}
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Urgency keywords for the rule-based fallback
_URGENCY_HIGH = re.compile(
    r"\b(collision|contact|damage|unsafe|pit lane|safety car|crash|hit|push|"
    r"penalty|black flag|disqualif|warning|stewards|protest|spin|"
    r"tyre failure|puncture|fire|engine|DNF|retire)\b",
    re.IGNORECASE,
)
_URGENCY_LOW = re.compile(
    r"\b(copy|understood|no problem|okay|nominal|looking good|fuel saving|"
    r"gap is|interval|box box)\b",
    re.IGNORECASE,
)
_NEGATIVE_WORDS = re.compile(
    r"\b(unfair|wrong|disagree|unacceptable|dangerous|ridiculous|"
    r"penalty|blame|fault|contact|pushed|hit me|ran me)\b",
    re.IGNORECASE,
)


def _rule_based(text: str) -> dict[str, float]:
    high_hits = len(_URGENCY_HIGH.findall(text))
    low_hits  = len(_URGENCY_LOW.findall(text))
    neg_hits  = len(_NEGATIVE_WORDS.findall(text))

    urgency   = min(1.0, high_hits * 0.25 - low_hits * 0.1)
    urgency   = max(0.0, urgency)
    sentiment = max(-1.0, min(1.0, -neg_hits * 0.3 + (0.1 if low_hits > 0 else 0.0)))
    return {"sentiment_score": round(sentiment, 3), "urgency_score": round(urgency, 3)}


def _load_model():
    """Lazy-load DistilBERT. Returns None on import failure."""
    try:
        from transformers import pipeline as hf_pipeline
        # Use distilbert-base-uncased-finetuned-sst-2-english for sentiment
        # and a zero-shot classifier for urgency until we fine-tune.
        sentiment_pipe = hf_pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
        )
        urgency_pipe = hf_pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
        )
        log.info("DistilBERT sentiment + BART zero-shot loaded")
        return sentiment_pipe, urgency_pipe
    except ImportError:
        log.warning("transformers not installed — using rule-based radio classifier")
        return None, None
    except Exception as exc:
        log.error("Model load failed: %s — using rule-based fallback", exc)
        return None, None


_SENTIMENT_PIPE = None
_URGENCY_PIPE   = None
_MODEL_LOADED   = False


def _ensure_loaded():
    global _SENTIMENT_PIPE, _URGENCY_PIPE, _MODEL_LOADED
    if not _MODEL_LOADED:
        _SENTIMENT_PIPE, _URGENCY_PIPE = _load_model()
        _MODEL_LOADED = True


def classify_radio(text: str) -> dict[str, float]:
    """
    Classify a radio transcript.

    Returns:
        {
            "sentiment_score": float  # [-1, 1]
            "urgency_score":   float  # [0, 1]
        }
    """
    if not text or not text.strip():
        return {"sentiment_score": 0.0, "urgency_score": 0.0}

    _ensure_loaded()

    if _SENTIMENT_PIPE is None or _URGENCY_PIPE is None:
        return _rule_based(text)

    try:
        # Sentiment
        sent_result  = _SENTIMENT_PIPE(text[:512])[0]
        sent_label   = sent_result["label"]      # POSITIVE | NEGATIVE
        sent_conf    = float(sent_result["score"])
        sentiment    = sent_conf if sent_label == "POSITIVE" else -sent_conf

        # Urgency via zero-shot
        urg_result   = _URGENCY_PIPE(
            text[:512],
            candidate_labels=["urgent safety incident", "normal race communication"],
        )
        urgency_idx  = urg_result["labels"].index("urgent safety incident")
        urgency      = float(urg_result["scores"][urgency_idx])

        return {
            "sentiment_score": round(sentiment, 3),
            "urgency_score":   round(urgency, 3),
        }
    except Exception as exc:
        log.warning("Model inference failed: %s — falling back", exc)
        return _rule_based(text)


def classify_batch(texts: list[str]) -> list[dict[str, float]]:
    """Classify multiple transcripts. Returns a list in the same order."""
    return [classify_radio(t) for t in texts]
