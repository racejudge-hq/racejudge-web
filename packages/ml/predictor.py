"""
Penalty prediction model — Phase 5.

Two-layer architecture from IMPLEMENTATION_PLAN.md:
  Layer A: XGBoost on tabular features (infraction type, telemetry, race context)
  Layer B: LLM reasoning (Llama-3-8B-Instruct + LoRA) — stub for Phase 5
  Meta:    Stacked logistic regression + Platt calibration on A+B outputs

Train/val/test split:
  train: 2018–2023, validate: 2024, test: 2025

Output: probability distribution over 7 classes + expected penalty-point delta
Target: Macro-F1 ≥ 0.65, ECE < 0.05

Usage:
    from packages.ml.predictor import PenaltyPredictor
    p = PenaltyPredictor.load("models/penalty_v1.pkl")
    result = p.predict(incident_record)
    # result = {"class": "5s", "proba": {...}, "penalty_points_delta": 1.2}

Dependencies (uncomment in requirements.txt when starting Phase 5):
    xgboost>=2.0.0
    scikit-learn>=1.4.0
    joblib>=1.4.0
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from packages.ml.features import (
    PENALTY_CLASSES,
    PENALTY_CLASS_TO_IDX,
    batch_extract_features,
    extract_features,
)

log = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
MODELS_DIR.mkdir(exist_ok=True)

# Categorical feature columns (will be one-hot encoded)
CAT_COLS = [
    "infraction_type",
    "article_cited",
    "session_type",
    "lap_phase",
    "corner_type",
    "weather",
    "tyre_compound",
]

# Numeric feature columns
NUM_COLS = [
    "speed_diff_kph",
    "braking_point_delta_m",
    "overlap_s",
    "drs_deployed",
    "position_change",
    "safety_car_out",
    "vsc_out",
    "penalty_points_ytd",
    "repeat_infraction",
]


def _require_sklearn():
    try:
        import sklearn
        return sklearn
    except ImportError:
        raise ImportError(
            "scikit-learn not installed. Uncomment scikit-learn>=1.4.0 "
            "in requirements.txt and run: pip install -r requirements.txt"
        )


def _require_xgboost():
    try:
        import xgboost
        return xgboost
    except ImportError:
        raise ImportError(
            "xgboost not installed. Uncomment xgboost>=2.0.0 "
            "in requirements.txt and run: pip install -r requirements.txt"
        )


def _build_pipeline(n_classes: int):
    """Build sklearn Pipeline: OneHotEncoder + StandardScaler + XGBClassifier."""
    _require_sklearn()
    _require_xgboost()

    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from xgboost import XGBClassifier

    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CAT_COLS),
            ("num", StandardScaler(), NUM_COLS),
        ]
    )

    clf = XGBClassifier(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="mlogloss",
        num_class=n_classes,
        objective="multi:softprob",
        random_state=42,
        n_jobs=-1,
        early_stopping_rounds=30,
    )

    return Pipeline([("prep", preprocessor), ("clf", clf)])


class PenaltyPredictor:
    """
    Wraps the XGBoost penalty prediction pipeline.
    Phase 5 will add the LLM layer and meta-stacker on top.
    """

    def __init__(self, pipeline=None, label_encoder=None):
        self._pipeline = pipeline
        self._label_encoder = label_encoder  # maps class idx → PENALTY_CLASSES

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    @classmethod
    def train(
        cls,
        records: list[dict],
        *,
        val_records: list[dict] | None = None,
        verbose: bool = True,
    ) -> "PenaltyPredictor":
        """
        Train on enriched incident records.
        records with penalty_class == None are skipped (unlabelled).
        """
        import pandas as pd

        feats = batch_extract_features(records)
        df = pd.DataFrame(feats)
        df = df[df["penalty_class"].notna()].copy()

        if df.empty:
            raise ValueError("No labelled records found (penalty_class is None for all)")

        log.info("Training on %d labelled records", len(df))

        X = df[CAT_COLS + NUM_COLS]
        y = df["penalty_class"].map(PENALTY_CLASS_TO_IDX)

        pipeline = _build_pipeline(n_classes=len(PENALTY_CLASSES))

        fit_kwargs: dict[str, Any] = {}
        if val_records:
            val_feats = batch_extract_features(val_records)
            val_df = pd.DataFrame(val_feats)
            val_df = val_df[val_df["penalty_class"].notna()].copy()
            if not val_df.empty:
                X_val = val_df[CAT_COLS + NUM_COLS]
                y_val = val_df["penalty_class"].map(PENALTY_CLASS_TO_IDX)
                fit_kwargs["clf__eval_set"] = [(pipeline["prep"].fit_transform(X), y),
                                               (pipeline["prep"].transform(X_val), y_val)]
                fit_kwargs["clf__verbose"] = verbose

        pipeline.fit(X, y, **fit_kwargs)
        log.info("Training complete")

        predictor = cls(pipeline=pipeline)
        return predictor

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, record: dict) -> dict[str, Any]:
        """
        Predict penalty for a single incident record.
        Returns dict with class prediction, probabilities, and expected pp delta.
        """
        if self._pipeline is None:
            raise RuntimeError("Model not trained. Call PenaltyPredictor.train() or .load() first")

        import pandas as pd

        feat = extract_features(record)
        X = pd.DataFrame([feat])[CAT_COLS + NUM_COLS]
        proba = self._pipeline.predict_proba(X)[0]

        class_idx = int(proba.argmax())
        predicted_class = PENALTY_CLASSES[class_idx]

        return {
            "predicted_class": predicted_class,
            "predicted_class_idx": class_idx,
            "proba": {cls: round(float(p), 4) for cls, p in zip(PENALTY_CLASSES, proba)},
            "confidence": round(float(proba.max()), 4),
            "penalty_points_delta": feat.get("penalty_points_delta", 0),
        }

    def predict_batch(self, records: list[dict]) -> list[dict]:
        return [self.predict(r) for r in records]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path | None = None) -> Path:
        import joblib
        path = Path(path) if path else MODELS_DIR / "penalty_v1.pkl"
        joblib.dump({"pipeline": self._pipeline}, path)
        log.info("Model saved to %s", path)
        return path

    @classmethod
    def load(cls, path: str | Path | None = None) -> "PenaltyPredictor":
        import joblib
        path = Path(path) if path else MODELS_DIR / "penalty_v1.pkl"
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        state = joblib.load(path)
        return cls(pipeline=state["pipeline"])

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate(
        records: list[dict],
        predictor: "PenaltyPredictor",
    ) -> dict[str, Any]:
        """
        Compute Macro-F1 and ECE on a held-out set.
        Gate: do not ship publicly if ECE >= 0.05.
        """
        from sklearn.metrics import classification_report, f1_score
        import numpy as np
        import pandas as pd

        feats = batch_extract_features(records)
        df = pd.DataFrame(feats)
        df = df[df["penalty_class"].notna()].copy()

        y_true = df["penalty_class"].map(PENALTY_CLASS_TO_IDX).values
        preds = predictor.predict_batch(df.to_dict("records"))
        y_pred = np.array([p["predicted_class_idx"] for p in preds])
        y_proba = np.array([[p["proba"][c] for c in PENALTY_CLASSES] for p in preds])

        macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
        ece = _compute_ece(y_true, y_proba, n_bins=10)

        report = classification_report(
            y_true, y_pred,
            target_names=PENALTY_CLASSES,
            zero_division=0,
            output_dict=True,
        )

        gate_pass = ece < 0.05

        return {
            "macro_f1": round(macro_f1, 4),
            "ece": round(ece, 4),
            "gate_pass": gate_pass,  # must be True before public ship
            "per_class": report,
            "n_samples": len(df),
        }


def _compute_ece(y_true, y_proba, n_bins: int = 10) -> float:
    """Expected Calibration Error (ECE)."""
    import numpy as np

    n_classes = y_proba.shape[1]
    ece = 0.0
    n = len(y_true)

    for c in range(n_classes):
        probs_c = y_proba[:, c]
        labels_c = (y_true == c).astype(float)
        bin_edges = np.linspace(0, 1, n_bins + 1)

        for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
            mask = (probs_c >= lo) & (probs_c < hi)
            if mask.sum() == 0:
                continue
            avg_conf = probs_c[mask].mean()
            avg_acc = labels_c[mask].mean()
            ece += (mask.sum() / n) * abs(avg_conf - avg_acc)

    return ece / n_classes
