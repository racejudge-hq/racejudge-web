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
from packages.ml.predictor import (  # noqa: E402
    CAT_COLS,
    NUM_COLS,
    _build_pipeline,
    _compute_ece,
    dense_label_space,
)
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


def db_context_map() -> dict[str, dict]:
    """Race context the JSONL corpus does not carry, keyed by doc_id.

    `position_change` is declared a model feature in `packages/ml/predictor.py`
    and read by `features.build_features` as a *top-level* key on the record.
    The scraper never writes one, so the feature was constantly 0 for every row
    of every training run — declared, one-hot'd, and carrying no information.

    It now exists: migration 0020 added `lap_features.position` from FastF1 and
    `scripts/backfill_position_change.py` derives the per-incident figure. This
    joins it back onto the records so the retrain can actually see it.

    Only real values are merged. An incident the timing cannot place keeps the
    0 default, which is also its meaning here -- no places changed -- so an
    absent value is not silently read as a gain or a loss.
    """
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT doc_id, position_change FROM incidents "
                "WHERE position_change IS NOT NULL")
    m: dict[str, dict] = {}
    for doc, pc in cur.fetchall():
        m.setdefault(doc, {"position_change": int(pc)})
    conn.close()
    return m


def merge_context(records: list[dict], ctx: dict[str, dict]) -> list[dict]:
    return [{**r, **ctx.get(r.get("doc_id"), {})} for r in records]


def build_xy(records, labelmap):
    df = pd.DataFrame(batch_extract_features(records))
    df["label"] = df["doc_id"].map(labelmap)
    df = df[df["label"].isin(PENALTY_CLASSES)].copy()
    return df[CAT_COLS + NUM_COLS], df["label"].map(PENALTY_CLASS_TO_IDX)


def evaluate(model, X, y, classes):
    """Score in the full PENALTY_CLASSES space, not the dense training one.

    A held-out year contains classes 2019-2023 never saw. Scoring in the dense
    space would quietly drop them; scoring in the full space counts them as the
    misses they are, which is the number worth reporting.
    """
    from sklearn.metrics import f1_score
    dense = model.predict_proba(X)
    proba = np.zeros((len(dense), len(PENALTY_CLASSES)))
    proba[:, classes] = dense
    pred = proba.argmax(1)
    return (f1_score(y, pred, average="macro", zero_division=0),
            _compute_ece(np.asarray(y), proba, n_bins=10), len(y))


def main() -> None:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.frozen import FrozenEstimator
    from sklearn.utils.class_weight import compute_sample_weight

    print("loading + parsing...", flush=True)
    ctx = db_context_map()
    train = merge_context(enrich_with_parser(load_records(DECISIONS_PATH, TRAIN)), ctx)
    val = merge_context(enrich_with_parser(load_records(DECISIONS_PATH, [VAL])), ctx)
    test = merge_context(enrich_with_parser(load_records(DECISIONS_PATH, [TEST])), ctx)
    lm = db_label_map()
    print(f"position_change available on {len(ctx)} decisions", flush=True)

    Xtr, ytr = build_xy(train, lm)
    Xval, yval = build_xy(val, lm)
    Xte, yte = build_xy(test, lm)
    print(f"labelled — train {len(ytr)} | val {len(yval)} | test {len(yte)}", flush=True)

    # DT is in no ruling before 2024, so the train split has a hole in its
    # label indices and XGBoost will not accept one. Train dense, score full.
    classes, dense = dense_label_space(ytr)
    print("classes trained: " + ", ".join(PENALTY_CLASSES[c] for c in classes), flush=True)
    ytr_d = ytr.map(dense)
    Xval_d, yval_d = Xval[yval.map(dense).notna()], yval.map(dense).dropna().astype(int)

    pipe = _build_pipeline(n_classes=len(classes))
    sw = compute_sample_weight("balanced", ytr_d)
    prep = pipe["prep"]
    pipe.fit(Xtr, ytr_d, clf__sample_weight=sw,
             clf__eval_set=[(prep.fit_transform(Xtr), ytr_d), (prep.transform(Xval_d), yval_d)],
             clf__verbose=False)

    model = pipe
    try:
        model = CalibratedClassifierCV(
            FrozenEstimator(pipe), method="sigmoid").fit(Xval_d, yval_d)
    except Exception as exc:  # noqa: BLE001
        print("calibration failed:", exc)

    for name, X, y in [("VAL 2024", Xval, yval), ("TEST 2025", Xte, yte)]:
        mf1, ece, n = evaluate(model, X, y, classes)
        print(f"  {name}: Macro-F1 {mf1:.4f} | ECE {ece:.4f} | n={n}", flush=True)

    mf1, ece, _ = evaluate(model, Xte, yte, classes)
    gate = mf1 >= 0.65 and ece < 0.05
    print("\n" + "=" * 56)
    print(f"DB-LABEL RETRAIN (test 2025): Macro-F1 {mf1:.4f} | ECE {ece:.4f}")
    print(f"SHIP GATE (Macro-F1>=0.65 AND ECE<0.05): {'PASS' if gate else 'FAIL'}")
    print("=" * 56)


if __name__ == "__main__":
    main()
