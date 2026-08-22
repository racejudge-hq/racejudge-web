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
    PENALTY_CLASS_TO_IDX,
    PENALTY_CLASSES,
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
    except ImportError as exc:
        raise ImportError(
            "scikit-learn not installed. Uncomment scikit-learn>=1.4.0 "
            "in requirements.txt and run: pip install -r requirements.txt"
        ) from exc


def _require_xgboost():
    try:
        import xgboost
        return xgboost
    except ImportError as exc:
        raise ImportError(
            "xgboost not installed. Uncomment xgboost>=2.0.0 "
            "in requirements.txt and run: pip install -r requirements.txt"
        ) from exc


def dense_label_space(y_full) -> tuple[list[int], dict[int, int]]:
    """Map the PENALTY_CLASSES indices actually present onto a gapless 0..k-1.

    XGBoost's sklearn wrapper infers its classes from `y` and rejects a label
    set with a hole in it ("Expected: [0 1 2 3 4 5], got [0 1 2 3 5 6]").
    A hole is normal here: DT appears in no ruling before 2024, so a train
    split of 2019-2023 simply has no example of class 4.

    Returns the present classes in full-space order and the forward map.
    `PenaltyPredictor` keeps the first so `predict` can put the columns back
    where the class names expect them -- see `_expand_proba`. Without that,
    every class after the hole is read under its neighbour's name.
    """
    classes = sorted({int(v) for v in y_full})
    return classes, {c: i for i, c in enumerate(classes)}


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

    def __init__(self, pipeline=None, label_encoder=None, calibrated=None):
        self._pipeline = pipeline
        self._label_encoder = label_encoder  # maps class idx → PENALTY_CLASSES
        self._calibrated = calibrated  # sigmoid-calibrated wrapper, optional

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
    ) -> PenaltyPredictor:
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
        y_full = df["penalty_class"].map(PENALTY_CLASS_TO_IDX)
        classes, dense = dense_label_space(y_full)
        y = y_full.map(dense)

        pipeline = _build_pipeline(n_classes=len(classes))

        fit_kwargs: dict[str, Any] = {}

        # Outcomes are heavily skewed towards NFA — without balancing the
        # model collapses to the majority class
        from sklearn.utils.class_weight import compute_sample_weight
        fit_kwargs["clf__sample_weight"] = compute_sample_weight("balanced", y)
        if val_records:
            val_feats = batch_extract_features(val_records)
            val_df = pd.DataFrame(val_feats)
            val_df = val_df[val_df["penalty_class"].notna()].copy()
            if not val_df.empty:
                X_val = val_df[CAT_COLS + NUM_COLS]
                # Same dense space as the training labels, and rows whose class
                # the training split never saw are dropped rather than mapped
                # to NaN, which XGBoost reads as a label of its own.
                y_val = val_df["penalty_class"].map(PENALTY_CLASS_TO_IDX).map(dense)
                X_val, y_val = X_val[y_val.notna()], y_val.dropna().astype(int)
                fit_kwargs["clf__eval_set"] = [(pipeline["prep"].fit_transform(X), y),
                                               (pipeline["prep"].transform(X_val), y_val)]
                fit_kwargs["clf__verbose"] = verbose

        pipeline.fit(X, y, **fit_kwargs)
        log.info("Training complete")

        # Sigmoid-calibrate probabilities on the validation split (ECE gate)
        calibrated = None
        if val_records:
            val_feats = batch_extract_features(val_records)
            val_df = pd.DataFrame(val_feats)
            val_df = val_df[val_df["penalty_class"].notna()].copy()
            if len(val_df) >= 50:
                from sklearn.calibration import CalibratedClassifierCV
                from sklearn.frozen import FrozenEstimator

                X_val = val_df[CAT_COLS + NUM_COLS]
                y_val = val_df["penalty_class"].map(PENALTY_CLASS_TO_IDX).map(dense)
                X_val, y_val = X_val[y_val.notna()], y_val.dropna().astype(int)
                try:
                    calibrated = CalibratedClassifierCV(
                        FrozenEstimator(pipeline), method="sigmoid"
                    )
                    calibrated.fit(X_val, y_val)
                    log.info("Probability calibration fitted on %d val records", len(val_df))
                except Exception as exc:
                    log.warning("Calibration failed (%s) — using raw probabilities", exc)
                    calibrated = None

        return cls(pipeline=pipeline, label_encoder=classes, calibrated=calibrated)

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
        model = self._calibrated if self._calibrated is not None else self._pipeline
        proba = self._expand_proba(model.predict_proba(X)[0])

        class_idx = int(proba.argmax())
        predicted_class = PENALTY_CLASSES[class_idx]

        return {
            "predicted_class": predicted_class,
            "predicted_class_idx": class_idx,
            # strict: the columns and the names must line up exactly. They did
            # not when a class was missing from training, and strict=False hid
            # it by truncating the names instead of raising.
            "proba": {cls: round(float(p), 4) for cls, p in zip(PENALTY_CLASSES, proba, strict=True)},
            "confidence": round(float(proba.max()), 4),
            "penalty_points_delta": feat.get("penalty_points_delta", 0),
        }

    def _expand_proba(self, proba):
        """Put a dense probability row back into full PENALTY_CLASSES order.

        A class the training split never contained gets 0.0 -- the model has
        no evidence for it, which is the honest value, and it keeps every
        other class under its own name.
        """
        import numpy as np

        if self._label_encoder is None or len(proba) == len(PENALTY_CLASSES):
            return proba
        full = np.zeros(len(PENALTY_CLASSES), dtype=float)
        for dense_idx, full_idx in enumerate(self._label_encoder):
            full[full_idx] = proba[dense_idx]
        return full

    def predict_batch(self, records: list[dict]) -> list[dict]:
        return [self.predict(r) for r in records]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path | None = None) -> Path:
        import joblib
        path = Path(path) if path else MODELS_DIR / "penalty_v1.pkl"
        joblib.dump({"pipeline": self._pipeline, "calibrated": self._calibrated,
                     "label_encoder": self._label_encoder}, path)
        log.info("Model saved to %s", path)
        return path

    @classmethod
    def load(cls, path: str | Path | None = None) -> PenaltyPredictor:
        import joblib
        path = Path(path) if path else MODELS_DIR / "penalty_v1.pkl"
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        state = joblib.load(path)
        # A model saved before the label space was stored covers all classes,
        # which is what a missing key means here.
        return cls(pipeline=state["pipeline"], calibrated=state.get("calibrated"),
                   label_encoder=state.get("label_encoder"))

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate(
        records: list[dict],
        predictor: PenaltyPredictor,
    ) -> dict[str, Any]:
        """
        Compute Macro-F1 and ECE on a held-out set.
        Gate: do not ship publicly if ECE >= 0.05.
        """
        import numpy as np
        from sklearn.metrics import classification_report, f1_score

        # Predict on the ORIGINAL records — extract_features() expects raw
        # decision records, not already-extracted feature dicts
        feats = batch_extract_features(records)
        labelled = [
            (rec, f) for rec, f in zip(records, feats, strict=True)
            if f.get("penalty_class") is not None
        ]
        if not labelled:
            return {"macro_f1": 0.0, "ece": 1.0, "gate_pass": False,
                    "per_class": {}, "n_samples": 0}

        raw_records = [rec for rec, _ in labelled]
        y_true = np.array([PENALTY_CLASS_TO_IDX[f["penalty_class"]] for _, f in labelled])

        preds = predictor.predict_batch(raw_records)
        y_pred = np.array([p["predicted_class_idx"] for p in preds])
        y_proba = np.array([[p["proba"][c] for c in PENALTY_CLASSES] for p in preds])

        macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
        ece = _compute_ece(y_true, y_proba, n_bins=10)

        report = classification_report(
            y_true, y_pred,
            labels=list(range(len(PENALTY_CLASSES))),
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
            "n_samples": len(labelled),
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

        for lo, hi in zip(bin_edges[:-1], bin_edges[1:], strict=False):
            mask = (probs_c >= lo) & (probs_c < hi)
            if mask.sum() == 0:
                continue
            avg_conf = probs_c[mask].mean()
            avg_acc = labels_c[mask].mean()
            ece += (mask.sum() / n) * abs(avg_conf - avg_acc)

    return ece / n_classes
