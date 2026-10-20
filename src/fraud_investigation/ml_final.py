"""Gel du pipeline CatBoost choisi, sans accès aux scores du test."""

from __future__ import annotations

import hashlib
import json
import platform
import time
from pathlib import Path

import catboost
import joblib
import numpy as np
import polars as pl
import sklearn
import xgboost

from fraud_investigation.ml_benchmark import TYPES, choose_threshold, scores
from fraud_investigation.ml_feature_ratio_recipient_history import RatioRecipientFeatures
from fraud_investigation.ml_recipient_history import counts_for_rows
from fraud_investigation.ml_tune_h import configured_model

CSV_SHA256 = "16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b"
FIT_END, THRESHOLD_END, TEST_START, TEST_END = 360, 432, 505, 743
MODEL_CONFIG = "cat_slow200"
SOURCE_COLUMNS = ("step", "type", "amount", "oldbalanceOrg", "nameDest", "isFraud")
MODEL_COLUMNS = ("type", "amount", "oldbalanceOrg", "hour_sin", "hour_cos",
                 "part_solde", "nb_entrees_anterieures")


def sha256(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def arrays(frame):
    """Coder type comme dans H, sans transformer les labels en variables."""
    step = frame["step"].to_numpy().astype(np.int16)
    amount = frame["amount"].to_numpy().astype(np.float32)
    balance = frame["oldbalanceOrg"].to_numpy().astype(np.float32)
    kind = np.full(len(step), 255, dtype=np.uint8)
    for code, name in enumerate(TYPES):
        kind[frame["type"].eq(name).to_numpy()] = code
    assert (kind != 255).all()
    assert np.isfinite(amount).all() and (amount >= 0).all()
    assert np.isfinite(balance).all() and (balance >= 0).all()
    return step, kind, amount, balance


def freeze(csv_path, output_dir):
    output_dir = Path(output_dir)
    model_path = output_dir / "pipeline.joblib"
    local_path = output_dir / "freeze_local.json"
    public_path = Path("docs/results/ml_final_manifest.json")
    if model_path.exists() or local_path.exists() or public_path.exists():
        raise FileExistsError("Un gel existe déjà ; aucun remplacement automatique")
    assert sha256(csv_path) == CSV_SHA256
    prior_result = json.loads(Path("docs/results/ml_tune_h_catboost.json").read_text())
    reference = next(r for r in prior_result["rows"]
                     if r["config"] == MODEL_CONFIG and r["fold"] == 5)
    assert reference["fit_steps"] == [1, FIT_END]
    assert reference["threshold_steps"] == [FIT_END+1, THRESHOLD_END]
    assert reference["validation_steps"] == [433, 504]
    frame = (pl.scan_csv(csv_path).filter(pl.col("step") <= THRESHOLD_END)
             .select(*SOURCE_COLUMNS).collect())
    assert frame.columns == list(SOURCE_COLUMNS) and frame.height == 6_008_416
    assert frame["step"].min() == 1 and frame["step"].max() == THRESHOLD_END
    assert frame.null_count().to_numpy().sum() == 0
    step, kind, amount, balance = arrays(frame)
    label = frame["isFraud"].to_numpy().astype(np.uint8)
    prior = counts_for_rows(frame.select("step", "nameDest")).to_numpy().astype(np.float32)
    fit, reserve = step <= FIT_END, step > FIT_END
    assert (int(fit.sum()), int(label[fit].sum())) == (reference["fit_rows"], reference["fit_frauds"])
    assert (int(reserve.sum()), int(label[reserve].sum())) == (reference["threshold_rows"], reference["threshold_frauds"])
    assert int((prior[fit] > 0).sum()) == reference["history_nonzero_rows"]["fit"]
    assert int((prior[reserve] > 0).sum()) == reference["history_nonzero_rows"]["threshold"]
    assert step[fit].max() < step[reserve].min()
    features = RatioRecipientFeatures("catboost").fit(kind[fit], amount[fit], balance[fit], prior[fit])
    assert features.columns == list(MODEL_COLUMNS) == reference["predictor_columns"]
    model = configured_model(MODEL_CONFIG)
    assert model.get_params() == reference["model_parameters"]
    started = time.perf_counter()
    x_fit = features.transform(kind[fit], amount[fit], balance[fit], step[fit], prior[fit])
    model.fit(x_fit, label[fit])
    fit_seconds = time.perf_counter() - started
    x_reserve = features.transform(kind[reserve], amount[reserve], balance[reserve],
                                   step[reserve], prior[reserve])
    reserve_scores = scores(model, x_reserve)
    threshold, internal_f1 = choose_threshold(label[reserve], reserve_scores)
    if threshold != reference["threshold"]:
        raise AssertionError(("Seuil reconstruit différent", threshold, reference["threshold"]))
    if abs(internal_f1 - reference["threshold_f1"]) > 1e-12:
        raise AssertionError("F1 de réserve différent")
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"features": features, "model": model, "threshold": threshold}, model_path,
                compress=0)
    reloaded = joblib.load(model_path)
    assert reloaded["threshold"] == threshold
    assert reloaded["features"].columns == features.columns
    reload_scores = scores(reloaded["model"], x_reserve)
    assert np.array_equal(reload_scores, reserve_scores)
    versions = {"python": platform.python_version(), "polars": pl.__version__,
                "numpy": np.__version__, "scikit_learn": sklearn.__version__,
                "xgboost": xgboost.__version__, "catboost": catboost.__version__}
    assert versions == reference["versions"]
    manifest = {"status": "frozen_before_test", "model_config": MODEL_CONFIG,
                "csv_sha256": CSV_SHA256, "pipeline_sha256": sha256(model_path),
                "artifact_location": "data/ml_final_catboost/pipeline.joblib (local, hors Git)",
                "source_columns": list(SOURCE_COLUMNS), "predictor_columns": features.columns,
                "model_parameters": model.get_params(), "versions": versions,
                "fit_steps": [1, FIT_END], "threshold_steps": [FIT_END+1, THRESHOLD_END],
                "selection_only_steps": [433, 504], "test_steps": [TEST_START, TEST_END],
                "fit_rows": int(fit.sum()), "fit_frauds": int(label[fit].sum()),
                "threshold_rows": int(reserve.sum()), "threshold_frauds": int(label[reserve].sum()),
                "threshold_rule": "F1 maximal, scores identiques groupés, seuil le plus haut à égalité",
                "threshold": threshold, "threshold_f1": internal_f1,
                "ratio_zero_balance": "NaN", "ratio_above_one": "unclipped",
                "recipient_history": "nameDest count at steps strictly less than current step",
                "reload_scores_equal": True, "test_evaluated": False}
    local_path.write_text(json.dumps({**manifest, "fit_seconds": fit_seconds}, indent=2) + "\n")
    public_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
