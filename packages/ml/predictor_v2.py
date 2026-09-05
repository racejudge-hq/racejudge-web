"""
Stacked penalty predictor v2 — Phase 5.

Combines XGBoost (Layer A) + Llama-3-8B LoRA (Layer B) with a logistic
regression meta-learner and Platt calibration. Falls back to Layer A only
when the LoRA adapter is not available.

Architecture:
  Layer A: XGBoost on tabular features  (predictor.py, models/penalty_v1.pkl)
  Layer B: Llama-3-8B LoRA on text     (train_llama_lora.py, models/llama-lora-penalty-v1/)
  Meta:    LogisticRegression on [A_proba, B_proba] → calibrated probability
  Final:   Platt scaling to ensure ECE < 0.05

Usage:
    # Train (after Layer A and Layer B are both trained):
    python -m packages.ml.predictor_v2 --train

    # Load for inference:
    from packages.ml.predictor_v2 import PredictorV2
    p = PredictorV2.load()
    result = p.predict(incident_record)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from packages.ml.features import PENALTY_CLASS_TO_IDX, PENALTY_CLASSES
from packages.ml.predictor import PenaltyPredictor

log = logging.getLogger(__name__)

MODELS_DIR          = Path(__file__).resolve().parents[2] / "models"
V2_MODEL_PATH       = MODELS_DIR / "penalty_v2.pkl"
LLAMA_ADAPTER_PATH  = MODELS_DIR / "llama-lora-penalty-v1"


# ---------------------------------------------------------------------------
# Meta-learner training
# ---------------------------------------------------------------------------

def train_meta(
    train_records: list[dict[str, Any]],
    layer_a_path:  str | Path = MODELS_DIR / "penalty_v1.pkl",
    adapter_path:  str | Path = LLAMA_ADAPTER_PATH,
    output_path:   str | Path = V2_MODEL_PATH,
) -> Path:
    """
    Train the stacked meta-learner.

    Steps:
      1. Get Layer A probabilities for all training records (tabular)
      2. Get Layer B probabilities for all training records (text)
      3. Stack [A_proba (7), B_proba (7)] → 14-dim feature
      4. Train LogisticRegression meta-learner
      5. Platt-calibrate on validation split
      6. Save combined model to output_path
    """
    import joblib
    import numpy as np
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression

    from packages.ml.train_llama_lora import LlamaLayerB

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading Layer A from %s ...", layer_a_path)
    layer_a = PenaltyPredictor.load(str(layer_a_path))

    log.info("Loading Layer B LoRA adapter from %s ...", adapter_path)
    try:
        layer_b = LlamaLayerB.load(str(adapter_path))
        use_layer_b = True
    except (FileNotFoundError, ImportError) as exc:
        log.warning("Layer B unavailable: %s — using Layer A only", exc)
        use_layer_b = False

    # Ground-truth labels
    y_true = [
        PENALTY_CLASS_TO_IDX.get(r.get("penalty_type", "NFA"), 0)
        for r in train_records
    ]

    log.info("Extracting Layer A probabilities (%d records) ...", len(train_records))
    a_proba_list: list[list[float]] = []
    for rec in train_records:
        result_a = layer_a.predict(rec)
        proba_a  = [result_a["proba"].get(c, 0.0) for c in PENALTY_CLASSES]
        a_proba_list.append(proba_a)
    A = np.array(a_proba_list)

    if use_layer_b:
        log.info("Extracting Layer B logits (%d records) ...", len(train_records))
        b_logits_list: list[list[float]] = []
        for rec in train_records:
            reasoning = rec.get("reasoning_text", "")
            if reasoning:
                logits = layer_b.predict_logits(reasoning)
            else:
                logits = dict.fromkeys(PENALTY_CLASSES, 0.0)
            b_logits_list.append([logits.get(c, 0.0) for c in PENALTY_CLASSES])
        B  = np.array(b_logits_list)
        # Softmax normalise B logits
        exp_B = np.exp(B - B.max(axis=1, keepdims=True))
        B_proba = exp_B / exp_B.sum(axis=1, keepdims=True)
        X_meta = np.hstack([A, B_proba])
    else:
        X_meta = A

    log.info("Training meta logistic regression on %d examples ...", len(X_meta))
    base_clf = LogisticRegression(
        C=1.0,
        max_iter=1000,
        multi_class="multinomial",
        solver="lbfgs",
    )
    # Platt calibration with cross-validation
    meta_clf = CalibratedClassifierCV(base_clf, cv=3, method="sigmoid")
    meta_clf.fit(X_meta, y_true)

    bundle = {
        "version":       "v2",
        "use_layer_b":   use_layer_b,
        "layer_a_path":  str(layer_a_path),
        "adapter_path":  str(adapter_path) if use_layer_b else None,
        "meta_clf":      meta_clf,
        "penalty_classes": PENALTY_CLASSES,
    }
    joblib.dump(bundle, output_path, compress=3)
    log.info("PredictorV2 saved to %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Inference class
# ---------------------------------------------------------------------------

class PredictorV2:
    """
    Stacked predictor with Layer A + optional Layer B.

    Falls back gracefully to Layer A when LoRA adapter or GPU is unavailable.
    """

    def __init__(self, bundle: dict):

        self._use_b   = bundle["use_layer_b"]
        self._meta    = bundle["meta_clf"]
        self._classes = bundle["penalty_classes"]

        self._layer_a = PenaltyPredictor.load(bundle["layer_a_path"])
        self._layer_b = None

        if self._use_b and bundle.get("adapter_path"):
            try:
                from packages.ml.train_llama_lora import LlamaLayerB
                self._layer_b = LlamaLayerB.load(bundle["adapter_path"])
            except Exception as exc:
                log.warning("Layer B load failed at inference: %s — using A only", exc)
                self._use_b = False

    @classmethod
    def load(cls, path: str | Path | None = None) -> PredictorV2:
        import joblib
        p = Path(path or V2_MODEL_PATH)
        if not p.exists():
            raise FileNotFoundError(
                f"PredictorV2 model not found at {p}.\n"
                "Train it first: python -m packages.ml.predictor_v2 --train"
            )
        bundle = joblib.load(p)
        return cls(bundle)

    def predict(self, incident_record: dict[str, Any]) -> dict[str, Any]:
        """
        Returns {class, proba, penalty_points_delta, model_version}.
        """
        import numpy as np

        # Layer A
        result_a = self._layer_a.predict(incident_record)
        proba_a  = np.array([[result_a["proba"].get(c, 0.0) for c in self._classes]])

        if self._use_b and self._layer_b is not None:
            reasoning = incident_record.get("reasoning_text", "")
            logits_b  = self._layer_b.predict_logits(reasoning or "")
            b_raw = np.array([[logits_b.get(c, 0.0) for c in self._classes]])
            exp_b = np.exp(b_raw - b_raw.max(axis=1, keepdims=True))
            proba_b = exp_b / exp_b.sum(axis=1, keepdims=True)
            X_meta = np.hstack([proba_a, proba_b])
        else:
            X_meta = proba_a

        meta_proba = self._meta.predict_proba(X_meta)[0]
        best_idx   = int(meta_proba.argmax())
        best_class = self._classes[best_idx]

        proba_dict = {c: float(meta_proba[i]) for i, c in enumerate(self._classes)}

        # Penalty points delta heuristic (same as v1)
        pts_map = {"NFA": 0, "REP": 0, "5s": 1, "10s": 2, "DT": 3, "GRID": 3, "DSQ": 12}
        pp_delta = sum(proba_dict.get(c, 0) * pts_map.get(c, 0) for c in self._classes)

        return {
            "class":                best_class,
            "confidence":           float(meta_proba[best_idx]),
            "proba":                proba_dict,
            "penalty_points_delta": round(pp_delta, 2),
            "model_version":        "v2" if self._use_b else "v2-layer-a-only",
        }


# ---------------------------------------------------------------------------
# Evaluation helper
# ---------------------------------------------------------------------------

def evaluate(predictor: PredictorV2, test_records: list[dict]) -> dict:
    """Compute macro-F1 and ECE on a test set."""
    import numpy as np

    preds, labels, probas = [], [], []
    for rec in test_records:
        result = predictor.predict(rec)
        preds.append(result["class"])
        labels.append(rec.get("penalty_type", "NFA"))
        probas.append([result["proba"].get(c, 0.0) for c in PENALTY_CLASSES])

    from sklearn.metrics import f1_score  # type: ignore[import]
    macro_f1 = f1_score(labels, preds, labels=PENALTY_CLASSES, average="macro", zero_division=0)

    # ECE: Expected Calibration Error (15 bins)
    probas_np = np.array(probas)
    y_idx = np.array([PENALTY_CLASS_TO_IDX.get(lbl, 0) for lbl in labels])
    confidences = probas_np.max(axis=1)
    correct     = (np.array([PENALTY_CLASS_TO_IDX.get(p, 0) for p in preds]) == y_idx).astype(float)

    bins = np.linspace(0, 1, 16)
    ece  = 0.0
    for i in range(len(bins) - 1):
        mask = (confidences >= bins[i]) & (confidences < bins[i + 1])
        if mask.sum() > 0:
            acc  = correct[mask].mean()
            conf = confidences[mask].mean()
            ece += (mask.sum() / len(labels)) * abs(acc - conf)

    return {"macro_f1": round(float(macro_f1), 4), "ece": round(float(ece), 4)}


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    import os
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Train / evaluate PredictorV2 stacked ensemble")
    parser.add_argument("--train",   action="store_true", help="Train the meta-learner")
    parser.add_argument("--eval",    action="store_true", help="Evaluate on test set")
    parser.add_argument("--layer-a", default=str(MODELS_DIR / "penalty_v1.pkl"))
    parser.add_argument("--adapter", default=str(LLAMA_ADAPTER_PATH))
    parser.add_argument("--output",  default=str(V2_MODEL_PATH))
    args = parser.parse_args()

    from pathlib import Path as _Path
    env_path = _Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set.")
        sys.exit(1)

    import psycopg2

    conn = psycopg2.connect(db_url)
    cur  = conn.cursor()
    cur.execute("""
        SELECT i.incident_id, i.reasoning_text, i.penalty_type,
               i.infraction_category, i.article_cited, i.lap, i.contact,
               d.season
        FROM incidents i
        JOIN decisions d ON i.doc_id = d.doc_id
        WHERE i.penalty_type IS NOT NULL
          AND i.reasoning_text IS NOT NULL
        -- published_at is the raw FIA string ("Published on08.10.23 20:58CET"),
        -- so ordering by it sorted every prefixed row after every bare one and
        -- then by day-of-month before month. published_at_utc is the same
        -- instant with a type (0022). NULLS LAST keeps a row whose date could
        -- not be parsed in the set rather than at the front of it.
        ORDER BY d.season, d.published_at_utc NULLS LAST
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    all_records = [
        {
            "incident_id":         r[0],
            "reasoning_text":      r[1],
            "penalty_type":        r[2],
            "infraction_type":     r[3],
            "article_cited":       r[4] or [],
            "lap":                 r[5],
            "contact":             r[6],
            "season":              r[7],
        }
        for r in rows
    ]

    train_recs = [r for r in all_records if r["season"] and r["season"] <= 2023]
    test_recs  = [r for r in all_records if r["season"] and r["season"] >= 2025]

    if args.train:
        output = train_meta(
            train_records=train_recs,
            layer_a_path=args.layer_a,
            adapter_path=args.adapter,
            output_path=args.output,
        )
        print(f"\nPredictorV2 saved to: {output}")
        print("\nRunning evaluation on 2025 test set...")
        p = PredictorV2.load(output)
        metrics = evaluate(p, test_recs)
        print(f"Macro-F1: {metrics['macro_f1']}   ECE: {metrics['ece']}")
        if metrics["macro_f1"] >= 0.65 and metrics["ece"] < 0.05:
            print("✅ Both gates passed — safe to enable ENABLE_PREDICTIONS=true")
        else:
            print("❌ Gate not passed — need more training data before enabling predictions")

    elif args.eval:
        p = PredictorV2.load(args.output)
        metrics = evaluate(p, test_recs)
        print(f"Macro-F1: {metrics['macro_f1']}   ECE: {metrics['ece']}")


if __name__ == "__main__":
    main()
