"""Expérience H : combiner E et les réceptions antérieures de G."""

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
    EXPECTED_COUNTS, FOLDS, TYPES, candidate, choose_threshold, metrics, scores,
)
from fraud_investigation.ml_feature_balance_share import ShareFeatures, balance_share
from fraud_investigation.ml_recipient_history import counts_for_rows

EXPERIMENT = "H_ratio_recipient_history"
MODELS = ("xgboost", "catboost")
SOURCE_COLUMNS = ("step", "type", "amount", "oldbalanceOrg", "nameDest", "isFraud")


def load_g_data(csv_path):
    """Lire uniquement les steps de développement, construire l'historique sans label."""
    start = time.perf_counter()
    frame = (pl.scan_csv(csv_path)
             .filter(pl.col("step") <= 504)
             .select(*SOURCE_COLUMNS)
             .collect())
    assert frame.columns == list(SOURCE_COLUMNS)
    assert frame.height == 6_064_036 and int(frame["isFraud"].sum()) == 5_621
    assert frame["step"].min() == 1 and frame["step"].max() == 504
    assert frame.null_count().to_numpy().sum() == 0
    read_seconds = time.perf_counter() - start
    history_start = time.perf_counter()
    prior_series = counts_for_rows(frame)
    history_seconds = time.perf_counter() - history_start
    history_rss = psutil.Process().memory_info().rss
    prior = prior_series.to_numpy().astype(np.float32)
    assert (prior >= 0).all() and np.isfinite(prior).all()
    assert (prior == np.floor(prior)).all()
    assert int((prior > 0).sum()) == 3_427_028 and int(prior.max()) == 112
    step = frame["step"].to_numpy().astype(np.int16)
    amount = frame["amount"].to_numpy().astype(np.float32)
    balance = frame["oldbalanceOrg"].to_numpy().astype(np.float32)
    label = frame["isFraud"].to_numpy().astype(np.uint8)
    assert np.isfinite(amount).all() and (amount >= 0).all()
    assert np.isfinite(balance).all() and (balance >= 0).all()
    kind = np.full(len(step), 255, dtype=np.uint8)
    for code, name in enumerate(TYPES):
        kind[frame["type"].eq(name).to_numpy()] = code
    assert (kind != 255).all()
    return step, kind, amount, balance, prior, label, {
        "read_seconds": read_seconds, "history_seconds": history_seconds,
        "history_rss_after_bytes": history_rss,
    }


class RatioRecipientFeatures:
    """Colonnes exactes de E suivies du compteur destinataire exact de G."""

    def __init__(self, name):
        if name not in MODELS:
            raise ValueError(name)
        self.name = name
        self.reference = ShareFeatures(name)
        self.columns = [*self.reference.columns, "nb_entrees_anterieures"]

    def fit(self, kind, amount, balance, prior):
        assert np.isfinite(prior).all() and (prior >= 0).all()
        self.reference.fit(kind, amount, balance)
        return self

    def transform(self, kind, amount, balance, step, prior):
        assert len(kind) == len(amount) == len(balance) == len(step) == len(prior)
        assert np.isfinite(prior).all() and (prior >= 0).all()
        base = self.reference.transform(kind, amount, balance, step)
        if self.name == "catboost":
            base["nb_entrees_anterieures"] = prior.astype(np.float32)
            assert list(base.columns) == self.columns
            return base
        result = np.column_stack((base, prior.astype(np.float32)))
        assert result.shape == (len(step), len(self.columns))
        return result


def run_one(csv_path, name, fold):
    if name not in MODELS or not 1 <= fold <= 5:
        raise ValueError((name, fold))
    start = time.perf_counter()
    step, kind, amount, balance, prior, label, construction = load_g_data(csv_path)
    fit_end, reserve_end, val_end = FOLDS[fold - 1]
    fit = step <= fit_end
    reserve = (step > fit_end) & (step <= reserve_end)
    validation = (step > reserve_end) & (step <= val_end)
    assert tuple((int(mask.sum()), int(label[mask].sum())) for mask in
                 (fit, reserve, validation)) == EXPECTED_COUNTS[fold - 1]
    assert step[fit].max() < step[reserve].min() <= step[reserve].max() < step[validation].min()
    assert all(label[mask].min() == 0 and label[mask].max() == 1
               for mask in (fit, reserve, validation))

    features = RatioRecipientFeatures(name).fit(kind[fit], amount[fit], balance[fit], prior[fit])
    model = candidate(name)
    build_start = time.perf_counter()
    x_fit = features.transform(kind[fit], amount[fit], balance[fit], step[fit], prior[fit])
    fit_build_seconds = time.perf_counter() - build_start
    fit_start = time.perf_counter()
    model.fit(x_fit, label[fit])
    fit_seconds = time.perf_counter() - fit_start
    fit_rss = psutil.Process().memory_info().rss
    del x_fit

    build_start = time.perf_counter()
    x_reserve = features.transform(kind[reserve], amount[reserve], balance[reserve],
                                   step[reserve], prior[reserve])
    threshold_build_seconds = time.perf_counter() - build_start
    threshold_start = time.perf_counter()
    reserve_scores = scores(model, x_reserve)
    threshold, internal_f1 = choose_threshold(label[reserve], reserve_scores)
    threshold_seconds = time.perf_counter() - threshold_start
    del x_reserve, reserve_scores

    build_start = time.perf_counter()
    x_validation = features.transform(kind[validation], amount[validation], balance[validation],
                                      step[validation], prior[validation])
    validation_build_seconds = time.perf_counter() - build_start
    predict_start = time.perf_counter()
    validation_scores = scores(model, x_validation)
    predict_seconds = time.perf_counter() - predict_start
    result = metrics(label[validation], validation_scores, threshold)
    serialized = io.BytesIO()
    joblib.dump({"features": features, "model": model}, serialized, compress=0)
    result.update({
        "experiment": EXPERIMENT, "model": name, "fold": fold,
        "source_columns": list(SOURCE_COLUMNS), "history_source_columns": ["step", "nameDest"],
        "predictor_columns": features.columns, "label_column": "isFraud",
        "raw_step_predictor": False, "raw_account_predictor": False,
        "fit_steps": [1, fit_end], "threshold_steps": [fit_end + 1, reserve_end],
        "validation_steps": [reserve_end + 1, val_end],
        "fit_rows": int(fit.sum()), "fit_frauds": int(label[fit].sum()),
        "threshold_rows": int(reserve.sum()), "threshold_frauds": int(label[reserve].sum()),
        "ratio_undefined_rows": {"fit": int((balance[fit] == 0).sum()),
                                 "threshold": int((balance[reserve] == 0).sum()),
                                 "validation": int((balance[validation] == 0).sum())},
        "ratio_above_one_rows": {"fit": int((balance_share(amount[fit], balance[fit]) > 1).sum()),
                                 "threshold": int((balance_share(amount[reserve], balance[reserve]) > 1).sum()),
                                 "validation": int((balance_share(amount[validation], balance[validation]) > 1).sum())},
        "history_nonzero_rows": {"fit": int((prior[fit] > 0).sum()),
                                 "threshold": int((prior[reserve] > 0).sum()),
                                 "validation": int((prior[validation] > 0).sum())},
        "threshold": threshold, "threshold_f1": internal_f1,
        "fit_build_seconds": fit_build_seconds,
        "threshold_build_seconds": threshold_build_seconds,
        "validation_build_seconds": validation_build_seconds,
        "fit_seconds": fit_seconds, "threshold_seconds": threshold_seconds,
        "predict_seconds": predict_seconds, "total_seconds": time.perf_counter() - start,
        "fit_rss_bytes": fit_rss, "end_rss_bytes": psutil.Process().memory_info().rss,
        "serialized_bytes": serialized.tell(), "random_seed": 42,
        "model_parameters": {key: ("NaN" if isinstance(value, float) and np.isnan(value)
                                  else value) for key, value in model.get_params().items()},
        "versions": {"python": platform.python_version(), "polars": pl.__version__,
                     "numpy": np.__version__, "scikit_learn": sklearn.__version__,
                     "xgboost": xgboost.__version__, "catboost": catboost.__version__},
        **construction,
    })
    return result
