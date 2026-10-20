"""Scoring chronologique du test réservé après gel du pipeline."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import polars as pl

from fraud_investigation.ml_benchmark import TYPES, metrics, scores
from fraud_investigation.ml_final import (
    CSV_SHA256, MODEL_COLUMNS, TEST_END, TEST_START, arrays, sha256,
)

TEST_ROWS, TEST_FRAUDS = 298_584, 2_592
TEST_COLUMNS = ("step", "type", "amount", "oldbalanceOrg", "nameDest", "isFraud")
PERIODS = ((505, 672), (673, 720), (721, 743))
AMOUNT_BUCKETS = ("0", "(0, 100000)", "[100000, 10^5.5)",
                  "[10^5.5, 1000000)", "[1000000, 10^6.5)", "[10^6.5, +inf)")


def amount_bucket(amount):
    """Regrouper les tranches logarithmiques EDA annoncées avant le test."""
    amount = np.asarray(amount)
    assert np.isfinite(amount).all() and (amount >= 0).all()
    positive_bucket = np.searchsorted(
        np.array([100_000, 10**5.5, 1_000_000, 10**6.5]), amount, side="right") + 1
    return np.where(amount == 0, 0, positive_bucket).astype(np.uint8)


def stepwise_history(names, steps, initial_counts):
    """Donner les compteurs avant chaque step, puis mettre ce step en mémoire."""
    names = np.asarray(names, dtype=object)
    steps = np.asarray(steps)
    if len(names) != len(steps) or len(names) == 0 or (steps < TEST_START).any():
        raise ValueError("Steps de test et noms requis")
    counts = Counter(initial_counts)
    for step in np.unique(steps):
        indices = np.flatnonzero(steps == step)
        current = names[indices]
        prior = np.fromiter((counts[name] for name in current), dtype=np.float32,
                            count=len(current))
        assert np.isfinite(prior).all() and (prior >= 0).all()
        yield int(step), indices, prior
        counts.update(current.tolist())


def subgroup(label, prediction_score, threshold, mask):
    if not mask.any():
        return {"transactions": 0, "frauds": 0, "prevalence": None,
                "alerts": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0,
                "precision": None, "recall": None, "f1": None}
    row = metrics(label[mask], prediction_score[mask], threshold)
    assert row["tp"]+row["fn"] == row["frauds"]
    assert row["tn"]+row["fp"] == row["transactions"]-row["frauds"]
    return row


def evaluate(csv_path, output_dir):
    output_dir = Path(output_dir)
    model_path = output_dir / "pipeline.joblib"
    attempt_path = output_dir / "test_attempt.json"
    predictions_path = output_dir / "test_predictions.npz"
    result_path = Path("docs/results/ml_final_test.json")
    if attempt_path.exists() or predictions_path.exists() or result_path.exists():
        raise FileExistsError("Une évaluation ou tentative existe déjà ; aucun remplacement automatique")
    manifest = json.loads(Path("docs/results/ml_final_manifest.json").read_text())
    assert manifest["status"] == "frozen_before_test" and manifest["test_evaluated"] is False
    assert manifest["csv_sha256"] == CSV_SHA256 == sha256(csv_path)
    assert manifest["pipeline_sha256"] == sha256(model_path)
    assert manifest["predictor_columns"] == list(MODEL_COLUMNS)
    assert manifest["fit_steps"] == [1, 360] and manifest["threshold_steps"] == [361, 432]
    assert manifest["selection_only_steps"] == [433, 504]
    assert manifest["test_steps"] == [TEST_START, TEST_END]
    frozen = joblib.load(model_path)
    features, model, threshold = frozen["features"], frozen["model"], frozen["threshold"]
    assert features.columns == list(MODEL_COLUMNS) and threshold == manifest["threshold"]
    assert model.get_params() == manifest["model_parameters"]
    # Cet état local survit à une erreur : aucune première tentative ne disparaît.
    attempt_path.write_text(json.dumps({"state": "started", "pipeline_sha256": manifest["pipeline_sha256"]},
                                       indent=2) + "\n")
    started = time.perf_counter()
    try:
        development = (pl.scan_csv(csv_path).filter(pl.col("step") <= 504)
                       .select("step", "nameDest").collect())
        assert development.height == 6_064_036 and development["step"].max() == 504
        grouped = development.group_by("nameDest").agg(pl.len().alias("count"))
        initial = dict(zip(grouped["nameDest"].to_list(), grouped["count"].to_list()))
        assert sum(initial.values()) == development.height
        del development, grouped
        frame = (pl.scan_csv(csv_path).filter(pl.col("step") >= TEST_START)
                 .select(*TEST_COLUMNS).collect())
        assert frame.columns == list(TEST_COLUMNS)
        assert frame.height == TEST_ROWS and int(frame["isFraud"].sum()) == TEST_FRAUDS
        assert frame["step"].min() == TEST_START and frame["step"].max() == TEST_END
        assert frame.null_count().to_numpy().sum() == 0
        # Le modèle et l'historique reçoivent exclusivement ces cinq colonnes sources.
        input_frame = frame.select("step", "type", "amount", "oldbalanceOrg", "nameDest")
        step, kind, amount, balance = arrays(input_frame)
        names = input_frame["nameDest"].to_numpy()
        raw_amount = frame["amount"].to_numpy()
        prediction_score = np.empty(len(step), dtype=np.float64)
        prior_for_audit = np.empty(len(step), dtype=np.float32)
        seen = np.zeros(len(step), dtype=bool)
        first_boundary_checked = False
        for current_step, indices, prior in stepwise_history(names, step, initial):
            assert not seen[indices].any()
            if current_step == TEST_START:
                assert np.array_equal(prior, np.fromiter((initial.get(name, 0) for name in names[indices]),
                                                         dtype=np.float32, count=len(indices)))
                first_boundary_checked = True
            x = features.transform(kind[indices], amount[indices], balance[indices],
                                   step[indices], prior)
            assert list(x.columns) == list(MODEL_COLUMNS)
            prediction_score[indices] = scores(model, x)
            prior_for_audit[indices] = prior
            seen[indices] = True
        assert seen.all() and first_boundary_checked
        assert len(np.unique(step)) == 239 and np.isfinite(prediction_score).all()
        # Les labels n'entrent qu'après l'achèvement de tous les scores.
        label = frame["isFraud"].to_numpy().astype(np.uint8)
        overall = subgroup(label, prediction_score, threshold, np.ones(len(label), dtype=bool))
        by_type = {name: subgroup(label, prediction_score, threshold,
                                  kind == index) for index, name in enumerate(TYPES)}
        bins = amount_bucket(raw_amount)
        by_amount = {name: subgroup(label, prediction_score, threshold,
                                    bins == index) for index, name in enumerate(AMOUNT_BUCKETS)}
        by_period = {f"{a}-{b}": subgroup(label, prediction_score, threshold,
                                          (step >= a) & (step <= b)) for a, b in PERIODS}
        for grouping in (by_type, by_amount, by_period):
            assert sum(r["transactions"] for r in grouping.values()) == TEST_ROWS
            assert sum(r["frauds"] for r in grouping.values()) == TEST_FRAUDS
            assert sum(r["tp"] for r in grouping.values()) == overall["tp"]
            assert sum(r["fp"] for r in grouping.values()) == overall["fp"]
        assert by_period["721-743"]["transactions"] == by_period["721-743"]["frauds"] == 272
        np.savez_compressed(predictions_path, score=prediction_score,
                            alert=(prediction_score >= threshold), label=label, step=step)
        result = {"status": "single_final_test", "model_config": manifest["model_config"],
                  "pipeline_sha256": manifest["pipeline_sha256"], "csv_sha256": CSV_SHA256,
                  "threshold": threshold, "test_steps": [TEST_START, TEST_END],
                  "history_initialization_steps": [1, 504],
                  "history_first_step_verified": first_boundary_checked,
                  "history_nonzero_rows": int((prior_for_audit > 0).sum()),
                  "overall": overall, "by_type": by_type, "by_amount": by_amount,
                  "amount_bucket_labels": list(AMOUNT_BUCKETS), "by_period": by_period,
                  "seconds": time.perf_counter() - started,
                  "individual_predictions": "data/ml_final_catboost/test_predictions.npz (local, hors Git)"}
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        attempt_path.write_text(json.dumps({"state": "completed", "pipeline_sha256": manifest["pipeline_sha256"],
                                           "result_location": "docs/results/ml_final_test.json"}, indent=2) + "\n")
        return result
    except Exception as error:
        attempt_path.write_text(json.dumps({"state": "failed", "pipeline_sha256": manifest["pipeline_sha256"],
                                           "error_type": type(error).__name__, "error": str(error)},
                                          indent=2) + "\n")
        raise
