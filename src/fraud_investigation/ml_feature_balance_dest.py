"""Expérience C : ajouter seulement oldbalanceDest à type et amount."""

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
    metrics, scores,
)


MODELS = ("xgboost", "catboost", "extra_trees", "random_forest")
EXPERIMENT = "C_oldbalanceDest"
SOURCE_COLUMNS = ("step", "type", "amount", "oldbalanceDest", "isFraud")


def load_balance_data(csv_path):
    """Ne lire que les colonnes permises et les steps des validations de développement."""
    frame = (pl.scan_csv(csv_path)
             .filter(pl.col("step") <= 504)
             .select(*SOURCE_COLUMNS)
             .collect())
    assert frame.height == 6_064_036
    assert int(frame["isFraud"].sum()) == 5_621
    assert frame["step"].min() == 1 and frame["step"].max() == 504
    assert frame.null_count().to_numpy().sum() == 0
    step = frame["step"].to_numpy().astype(np.int16)
    amount = frame["amount"].to_numpy().astype(np.float32)
    balance = frame["oldbalanceDest"].to_numpy().astype(np.float32)
    label = frame["isFraud"].to_numpy().astype(np.uint8)
    assert np.isfinite(amount).all() and (amount >= 0).all()
    assert np.isfinite(balance).all() and (balance >= 0).all()
    kind = np.full(len(step), 255, dtype=np.uint8)
    for code, name in enumerate(TYPES):
        kind[frame["type"].eq(name).to_numpy()] = code
    assert (kind != 255).all()
    return step, kind, amount, balance, label


class BalanceFeatures:
    """Prétraitement initial inchangé, puis ajout du seul solde destinataire."""

    def __init__(self, name):
        if name not in MODELS:
            raise ValueError(name)
        self.name = name
        self.reference = Features(name)
        self.columns = (["type", "amount", "oldbalanceDest"] if name == "catboost"
                        else [*(f"type_{item}" for item in TYPES),
                              "amount", "oldbalanceDest"])

    def fit(self, kind, amount, balance):
        self.reference.fit(kind, amount)
        return self

    def transform(self, kind, amount, balance):
        assert len(kind) == len(amount) == len(balance)
        assert np.isfinite(balance).all() and (balance >= 0).all()
        base = self.reference.transform(kind, amount)
        if self.name == "catboost":
            base["oldbalanceDest"] = balance
            assert list(base.columns) == self.columns
            return base
        result = np.column_stack((base, balance.reshape(-1, 1)))
        assert result.shape == (len(balance), len(self.columns))
        return result


def run_one(csv_path, name, fold):
    if name not in MODELS or not 1 <= fold <= 5:
        raise ValueError((name, fold))
    start = time.perf_counter()
    step, kind, amount, balance, label = load_balance_data(csv_path)
    fit_end, reserve_end, val_end = FOLDS[fold - 1]
    fit = step <= fit_end
    reserve = (step > fit_end) & (step <= reserve_end)
    validation = (step > reserve_end) & (step <= val_end)
    assert tuple((int(mask.sum()), int(label[mask].sum())) for mask in
                 (fit, reserve, validation)) == EXPECTED_COUNTS[fold - 1]
    assert step[fit].max() < step[reserve].min() <= step[reserve].max() < step[validation].min()
    assert all(label[mask].min() == 0 and label[mask].max() == 1
               for mask in (fit, reserve, validation))

    features = BalanceFeatures(name).fit(kind[fit], amount[fit], balance[fit])
    model = candidate(name)
    x_fit = features.transform(kind[fit], amount[fit], balance[fit])
    fit_start = time.perf_counter()
    model.fit(x_fit, label[fit])
    fit_seconds = time.perf_counter() - fit_start
    fit_rss = psutil.Process().memory_info().rss
    del x_fit

    x_reserve = features.transform(kind[reserve], amount[reserve], balance[reserve])
    reserve_start = time.perf_counter()
    reserve_scores = scores(model, x_reserve)
    threshold, internal_f1 = choose_threshold(label[reserve], reserve_scores)
    threshold_seconds = time.perf_counter() - reserve_start
    del x_reserve, reserve_scores

    x_validation = features.transform(kind[validation], amount[validation], balance[validation])
    predict_start = time.perf_counter()
    val_scores = scores(model, x_validation)
    predict_seconds = time.perf_counter() - predict_start
    result = metrics(label[validation], val_scores, threshold)
    serialized = io.BytesIO()
    joblib.dump({"features": features, "model": model}, serialized, compress=0)
    result.update({
        "experiment": EXPERIMENT, "model": name, "fold": fold,
        "source_columns": list(SOURCE_COLUMNS), "predictor_columns": features.columns,
        "label_column": "isFraud",
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
