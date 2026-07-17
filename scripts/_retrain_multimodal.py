"""
Retrain the penalty predictor with the real Phase 3 multimodal features and
compare honestly against the baseline (same split, same model, no enrichment).

Split (per IMPLEMENTATION_PLAN): train 2019-2023, val 2024, test 2025.
Prints baseline vs enriched Macro-F1 / ECE and the ship gate result.
Saves the enriched model to models/penalty_v2.pkl.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.ml.enrich import enrich_with_db  # noqa: E402
from packages.ml.predictor import PenaltyPredictor  # noqa: E402
from packages.ml.train import DECISIONS_PATH, enrich_with_parser, load_records  # noqa: E402

TRAIN_SEASONS = [2019, 2020, 2021, 2022, 2023]
VAL_SEASON = 2024
TEST_SEASON = 2025


def _fmt(m: dict) -> str:
    return (f"Macro-F1 {m['macro_f1']:.4f} | ECE {m['ece']:.4f} "
            f"| n={m['n_samples']} | gate_pass(ECE<0.05)={m['gate_pass']}")


def run(label: str, train, val, test):
    print(f"\n=== {label} ===", flush=True)
    predictor = PenaltyPredictor.train(train, val_records=val, verbose=False)
    val_m = PenaltyPredictor.evaluate(val, predictor)
    test_m = PenaltyPredictor.evaluate(test, predictor)
    print(f"  VAL  {VAL_SEASON}: {_fmt(val_m)}", flush=True)
    print(f"  TEST {TEST_SEASON}: {_fmt(test_m)}", flush=True)
    return predictor, test_m


def main() -> None:
    print("loading + parsing records...", flush=True)
    train = enrich_with_parser(load_records(DECISIONS_PATH, TRAIN_SEASONS))
    val = enrich_with_parser(load_records(DECISIONS_PATH, [VAL_SEASON]))
    test = enrich_with_parser(load_records(DECISIONS_PATH, [TEST_SEASON]))
    print(f"  train {len(train)} | val {len(val)} | test {len(test)}", flush=True)

    # Baseline: no multimodal enrichment (new feature cols stay 0).
    _, base_test = run("BASELINE (no multimodal data)", train, val, test)

    # Treatment: attach the real backfilled signals.
    print("\nenriching with DB multimodal signals...", flush=True)
    tr_e = enrich_with_db(train)
    val_e = enrich_with_db(val)
    test_e = enrich_with_db(test)
    n_rich = sum(1 for r in test_e if r.get("openf1", {}).get("weather_data", {}).get("air_temp") is not None)
    print(f"  test records with real weather attached: {n_rich}/{len(test_e)}", flush=True)
    pred, enr_test = run("ENRICHED (real telemetry/weather/radio/RC)", tr_e, val_e, test_e)

    pred.save(ROOT / "models" / "penalty_v2.pkl")

    print("\n" + "=" * 60)
    print("HONEST COMPARISON (test = 2025):")
    print(f"  baseline : Macro-F1 {base_test['macro_f1']:.4f} | ECE {base_test['ece']:.4f}")
    print(f"  enriched : Macro-F1 {enr_test['macro_f1']:.4f} | ECE {enr_test['ece']:.4f}")
    dmf = enr_test["macro_f1"] - base_test["macro_f1"]
    dece = enr_test["ece"] - base_test["ece"]
    print(f"  delta    : Macro-F1 {dmf:+.4f} | ECE {dece:+.4f}")
    gate = enr_test["macro_f1"] >= 0.65 and enr_test["ece"] < 0.05
    print(f"\n  SHIP GATE (Macro-F1>=0.65 AND ECE<0.05): {'PASS' if gate else 'FAIL'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
