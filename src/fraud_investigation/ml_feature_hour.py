"""Expérience A : ajouter uniquement l'heure simulée à la référence ML."""

from __future__ import annotations

import io
import platform
import time

import catboost
import joblib
import numpy as np
import polars as pl
import psutil
import sklearn
import xgboost

from fraud_investigation.ml_benchmark import (
    EXPECTED_COUNTS, FOLDS, TYPES, Features, candidate, choose_threshold,
    load_data, metrics, scores,
)


MODELS = ("xgboost", "catboost", "extra_trees", "random_forest", "knn")
EXPERIMENT = "A_hour"


def cyclic_hour(step: np.ndarray) -> np.ndarray:
    """Deux coordonnées pour une seule heure simulée, sans calendrier civil."""
    assert np.issubdtype(step.dtype, np.integer)
    assert np.all(step >= 1)
    hour = (step.astype(np.int32) - 1) % 24
    angle = 2 * np.pi * hour / 24
    return np.column_stack((np.sin(angle), np.cos(angle))).astype(np.float32)


class HourFeatures:
    def __init__(self, name: str):
        if name not in MODELS:
            raise ValueError(name)
        self.name = name
        self.reference = Features(name)
        self.columns = (["type", "amount", "hour_sin", "hour_cos"] if name == "catboost"
                        else [*(f"type_{item}" for item in TYPES),
                              "amount" if name != "knn" else "scaled_log1p_amount",
                              "hour_sin", "hour_cos"])

    def fit(self, kind: np.ndarray, amount: np.ndarray):
        self.reference.fit(kind, amount)
        return self

    def transform(self, kind: np.ndarray, amount: np.ndarray, step: np.ndarray):
        base = self.reference.transform(kind, amount)
        hour = cyclic_hour(step)
        if self.name == "catboost":
            base["hour_sin"] = hour[:, 0]
            base["hour_cos"] = hour[:, 1]
            assert list(base.columns) == self.columns
            return base
        result = np.column_stack((base, hour))
        assert result.shape == (len(step), len(self.columns))
        return result


def run_one(csv_path, name: str, fold: int):
    if name not in MODELS or not 1 <= fold <= 5:
        raise ValueError((name, fold))
    start = time.perf_counter()
    # load_data ne projette que step, type, amount et isFraud, jusqu'au step 504.
    step, kind, amount, label = load_data(csv_path)
    fit_end, reserve_end, val_end = FOLDS[fold - 1]
    fit = step <= fit_end
    reserve = (step > fit_end) & (step <= reserve_end)
    validation = (step > reserve_end) & (step <= val_end)
    assert tuple((int(mask.sum()), int(label[mask].sum())) for mask in
                 (fit, reserve, validation)) == EXPECTED_COUNTS[fold - 1]
    assert np.all(step[fit] < step[reserve].min())
    assert np.all(step[reserve] < step[validation].min())
    assert all(label[mask].min() == 0 and label[mask].max() == 1
               for mask in (fit, reserve, validation))

    features = HourFeatures(name).fit(kind[fit], amount[fit])
    model = candidate(name)
    x_fit = features.transform(kind[fit], amount[fit], step[fit])
    fit_start = time.perf_counter()
    model.fit(x_fit, label[fit])
    fit_seconds = time.perf_counter() - fit_start
    fit_rss = psutil.Process().memory_info().rss
    del x_fit

    x_reserve = features.transform(kind[reserve], amount[reserve], step[reserve])
    reserve_start = time.perf_counter()
    reserve_scores = scores(model, x_reserve)
    threshold, internal_f1 = choose_threshold(label[reserve], reserve_scores)
    threshold_seconds = time.perf_counter() - reserve_start
    del x_reserve, reserve_scores

    x_validation = features.transform(kind[validation], amount[validation], step[validation])
    predict_start = time.perf_counter()
    val_scores = scores(model, x_validation)
    predict_seconds = time.perf_counter() - predict_start
    result = metrics(label[validation], val_scores, threshold)
    serialized = io.BytesIO()
    joblib.dump({"features": features, "model": model}, serialized, compress=0)
    result.update({
        "experiment": EXPERIMENT, "model": name, "fold": fold,
        "source_columns": ["step", "type", "amount", "isFraud"],
        "predictor_columns": features.columns,
        "label_column": "isFraud", "raw_step_predictor": False,
        "fit_steps": [1, fit_end], "threshold_steps": [fit_end + 1, reserve_end],
        "validation_steps": [reserve_end + 1, val_end],
        "fit_rows": int(fit.sum()), "fit_frauds": int(label[fit].sum()),
        "threshold_rows": int(reserve.sum()), "threshold_frauds": int(label[reserve].sum()),
        "threshold": threshold, "threshold_f1": internal_f1,
        "fit_seconds": fit_seconds, "threshold_seconds": threshold_seconds,
        "predict_seconds": predict_seconds, "total_seconds": time.perf_counter() - start,
        "fit_rss_bytes": fit_rss, "end_rss_bytes": psutil.Process().memory_info().rss,
        "serialized_bytes": serialized.tell(), "random_seed": 42,
        "model_parameters": {key: ("NaN" if isinstance(value, float) and np.isnan(value)
                                  else value) for key, value in model.get_params().items()},
        "versions": {"python": platform.python_version(), "polars": pl.__version__,
                     "numpy": np.__version__, "scikit_learn": sklearn.__version__,
                     "xgboost": xgboost.__version__, "catboost": catboost.__version__},
    })
    return result
