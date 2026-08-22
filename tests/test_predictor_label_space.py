"""The label space the model trains on vs the one its callers read.

XGBoost emits one probability column per class *present in the training split*.
`PENALTY_CLASSES` has seven, and no ruling before 2024 imposes a drive-through,
so a 2019-2023 train split produces six columns. Everything here exists because
that mismatch used to be silent: `zip(..., strict=False)` truncated the names
and reported GRID's probability as DT.
"""

import numpy as np

from packages.ml.features import PENALTY_CLASSES
from packages.ml.predictor import PenaltyPredictor, dense_label_space

DT = PENALTY_CLASSES.index("DT")


def test_a_gapped_label_set_becomes_gapless():
    classes, dense = dense_label_space([0, 1, 2, 3, 5, 6])
    assert classes == [0, 1, 2, 3, 5, 6]
    assert sorted(dense.values()) == [0, 1, 2, 3, 4, 5]
    assert dense[5] == 4 and dense[6] == 5


def test_the_mapping_survives_unsorted_and_repeated_labels():
    classes, dense = dense_label_space([6, 0, 6, 2, 0])
    assert classes == [0, 2, 6]
    assert dense == {0: 0, 2: 1, 6: 2}


def test_every_class_keeps_its_own_name_when_one_is_missing():
    # Six columns for the six classes trained; the seventh, DT, was never seen.
    classes = [i for i in range(len(PENALTY_CLASSES)) if i != DT]
    dense_row = np.array([0.1, 0.1, 0.2, 0.1, 0.4, 0.1])
    full = PenaltyPredictor(label_encoder=classes)._expand_proba(dense_row)

    assert len(full) == len(PENALTY_CLASSES)
    for dense_idx, full_idx in enumerate(classes):
        assert full[full_idx] == dense_row[dense_idx]


def test_a_class_absent_from_training_gets_no_probability():
    classes = [i for i in range(len(PENALTY_CLASSES)) if i != DT]
    full = PenaltyPredictor(label_encoder=classes)._expand_proba(np.full(6, 1 / 6))
    # The model has no evidence for DT, and 0.0 says exactly that.
    assert full[DT] == 0.0
    assert np.isclose(full.sum(), 1.0)


def test_the_argmax_names_the_class_the_model_actually_chose():
    classes = [i for i in range(len(PENALTY_CLASSES)) if i != DT]
    # Highest column is dense index 5 — GRID under the old truncated zip, DSQ in truth.
    row = np.array([0.05, 0.05, 0.05, 0.05, 0.1, 0.7])
    full = PenaltyPredictor(label_encoder=classes)._expand_proba(row)
    assert PENALTY_CLASSES[int(full.argmax())] == "DSQ"


def test_a_full_width_row_is_left_alone():
    row = np.arange(len(PENALTY_CLASSES), dtype=float)
    for encoder in (None, list(range(len(PENALTY_CLASSES)))):
        assert np.array_equal(PenaltyPredictor(label_encoder=encoder)._expand_proba(row), row)
