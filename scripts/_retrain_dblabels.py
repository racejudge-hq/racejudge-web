"""
Best-effort attempt to lift the penalty predictor past the ship gate using the
clean DB-extracted penalty_type labels (more + less noisy than the regex parser
the default trainer uses). Same split: train 2019-2023, val 2024, test 2025.
Honest report — prints real Macro-F1 / ECE per split, no fabrication.
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.ml.features import (  # noqa: E402
    PENALTY_CLASS_TO_IDX,
    PENALTY_CLASSES,
    batch_extract_features,
)
from packages.ml.predictor import CAT_COLS, NUM_COLS, _build_pipeline, _compute_ece  # noqa: E402
from packages.ml.train import DECISIONS_PATH, enrich_with_parser, load_records  # noqa: E402

TRAIN, VAL, TEST = [2019, 2020, 2021, 2022, 2023], 2024, 2025


def db_label_map() -> dict[str, str]:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT doc_id, penalty_type FROM incidents "
                "WHERE penalty_type IS NOT NULL AND penalty_type <> ''")
    m: dict[str, str] = {}
    for doc, pt in cur.fetchall():
        m.setdefault(doc, pt)        # first/primary label per decision
    conn.close()
    return m


def build_xy(records, labelmap):
    df = pd.DataFrame(batch_extract_features(records))
    df["label"] = df["doc_id"].map(labelmap)
    df = df[df["label"].isin(PENALTY_CLASSES)].copy()
    return df[CAT_COLS + NUM_COLS], df["label"].map(PENALTY_CLASS_TO_IDX)


def evaluate(model, X, y):
    from sklearn.metrics import f1_score
    proba = model.predict_proba(X)
    pred = proba.argmax(1)
    return (f1_score(y, pred, average="macro", zero_division=0),
            _compute_ece(np.asarray(y), proba, n_bins=10), len(y))


def main() -> None:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.frozen import FrozenEstimator
    from sklearn.utils.class_weight import compute_sample_weight

    print("loading + parsing...", flush=True)
    train = enrich_with_parser(load_records(DECISIONS_PATH, TRAIN))
    val = enrich_with_parser(load_records(DECISIONS_PATH, [VAL]))
    test = enrich_with_parser(load_records(DECISIONS_PATH, [TEST]))
    lm = db_label_map()

    Xtr, ytr = build_xy(train, lm)
    Xval, yval = build_xy(val, lm)
    Xte, yte = build_xy(test, lm)
    print(f"labelled — train {len(ytr)} | val {len(yval)} | test {len(yte)}", flush=True)

    pipe = _build_pipeline(n_classes=len(PENALTY_CLASSES))
    sw = compute_sample_weight("balanced", ytr)
    prep = pipe["prep"]
    pipe.fit(Xtr, ytr, clf__sample_weight=sw,
             clf__eval_set=[(prep.fit_transform(Xtr), ytr), (prep.transform(Xval), yval)],
             clf__verbose=False)

    model = pipe
    try:
        model = CalibratedClassifierCV(FrozenEstimator(pipe), method="sigmoid").fit(Xval, yval)
    except Exception as exc:  # noqa: BLE001
        print("calibration failed:", exc)

    for name, X, y in [("VAL 2024", Xval, yval), ("TEST 2025", Xte, yte)]:
        mf1, ece, n = evaluate(model, X, y)
        print(f"  {name}: Macro-F1 {mf1:.4f} | ECE {ece:.4f} | n={n}", flush=True)

    mf1, ece, _ = evaluate(model, Xte, yte)
    gate = mf1 >= 0.65 and ece < 0.05
    print("\n" + "=" * 56)
    print(f"DB-LABEL RETRAIN (test 2025): Macro-F1 {mf1:.4f} | ECE {ece:.4f}")
    print(f"SHIP GATE (Macro-F1>=0.65 AND ECE<0.05): {'PASS' if gate else 'FAIL'}")
    print("=" * 56)


if __name__ == "__main__":
    main()
