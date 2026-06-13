"""
Penalty prediction model training script — Phase 5.

Train/val/test split: train 2018–2023, validate 2024, test 2025.
Uses the extracted + parsed JSONL data from data/parsed/decisions.jsonl.

Usage:
    python -m packages.ml.train
    python -m packages.ml.train --train-seasons 2018,2019,2020,2021,2022,2023 \
                                --val-season 2024 --test-season 2025
    python -m packages.ml.train --evaluate-only models/penalty_v1.pkl

Gate: do not ship publicly if ECE >= 0.05 (printed at end).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

DECISIONS_PATH = ROOT / "data" / "parsed" / "decisions.jsonl"


def load_records(path: Path, seasons: list[int] | None = None) -> list[dict]:
    """Load JSONL decisions and optionally filter by season."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if seasons and rec.get("season") not in seasons:
                continue
            records.append(rec)
    return records


def enrich_with_parser(records: list[dict]) -> list[dict]:
    """Run decision_parser on records that don't have parsed fields yet."""
    from packages.pipeline.parsers.decision_parser import extract_incident
    enriched = []
    for rec in records:
        # `parsed` may exist but be null (scraper writes raw records) —
        # treat empty as unparsed, not just a missing key
        if not rec.get("parsed"):
            parsed = extract_incident(rec)
            rec = {**rec, "parsed": parsed}
        enriched.append(rec)
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(description="Train or evaluate penalty prediction model")
    parser.add_argument(
        "--train-seasons",
        default="2018,2019,2020,2021,2022,2023",
        help="Comma-separated training seasons",
    )
    parser.add_argument("--val-season", type=int, default=2024)
    parser.add_argument("--test-season", type=int, default=2025)
    parser.add_argument(
        "--evaluate-only",
        type=Path,
        help="Path to saved model — skip training, just evaluate",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "models" / "penalty_v1.pkl",
        help="Where to save the trained model",
    )
    args = parser.parse_args()

    if not DECISIONS_PATH.exists():
        log.error("No decisions.jsonl found at %s — run the scraper first.", DECISIONS_PATH)
        sys.exit(1)

    train_seasons = [int(s) for s in args.train_seasons.split(",")]
    log.info("Loading records...")

    train_records = enrich_with_parser(load_records(DECISIONS_PATH, train_seasons))
    val_records = enrich_with_parser(load_records(DECISIONS_PATH, [args.val_season]))
    test_records = enrich_with_parser(load_records(DECISIONS_PATH, [args.test_season]))

    log.info(
        "Dataset — train: %d, val: %d, test: %d",
        len(train_records), len(val_records), len(test_records),
    )

    from packages.ml.predictor import PenaltyPredictor

    if args.evaluate_only:
        log.info("Evaluate-only mode — loading model from %s", args.evaluate_only)
        predictor = PenaltyPredictor.load(args.evaluate_only)
    else:
        log.info("Training model on seasons %s...", train_seasons)
        predictor = PenaltyPredictor.train(
            train_records,
            val_records=val_records if val_records else None,
            verbose=True,
        )
        model_path = predictor.save(args.output)
        log.info("Model saved to %s", model_path)

    # Evaluate on validation set
    if val_records:
        log.info("Evaluating on val (season %d)...", args.val_season)
        val_metrics = PenaltyPredictor.evaluate(val_records, predictor)
        _print_metrics("Validation", val_metrics)

    # Evaluate on test set
    if test_records:
        log.info("Evaluating on test (season %d)...", args.test_season)
        test_metrics = PenaltyPredictor.evaluate(test_records, predictor)
        _print_metrics("Test", test_metrics)

        ece = test_metrics["ece"]
        macro_f1 = test_metrics["macro_f1"]
        gate_pass = test_metrics["gate_pass"]

        print("\n" + "=" * 50)
        print(f"SHIP GATE: {'✓ PASS' if gate_pass else '✗ FAIL'}")
        print(f"  Macro-F1: {macro_f1:.4f} (target ≥ 0.65)")
        print(f"  ECE:      {ece:.4f} (target < 0.05)")
        if not gate_pass:
            print("\n  DO NOT ship publicly — ECE ≥ 0.05")
        print("=" * 50)
        sys.exit(0 if gate_pass else 1)


def _print_metrics(split: str, metrics: dict) -> None:
    print(f"\n{split} metrics ({metrics['n_samples']} samples):")
    print(f"  Macro-F1 : {metrics['macro_f1']:.4f}")
    print(f"  ECE      : {metrics['ece']:.4f}")
    per_class = metrics.get("per_class", {})
    print("  Per-class F1:")
    for cls in ["NFA", "REP", "5s", "10s", "DT", "GRID", "DSQ"]:
        if cls in per_class:
            f1 = per_class[cls].get("f1-score", 0)
            sup = per_class[cls].get("support", 0)
            print(f"    {cls:6s}: {f1:.3f}  (n={sup})")


if __name__ == "__main__":
    main()
