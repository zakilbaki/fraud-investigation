"""Réglages prédéfinis de H, sans changement de variables."""

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
    EXPECTED_COUNTS, FOLDS, candidate, choose_threshold, metrics, scores,
)
from fraud_investigation.ml_feature_balance_share import balance_share
from fraud_investigation.ml_feature_ratio_recipient_history import (
    RatioRecipientFeatures, SOURCE_COLUMNS, load_g_data,
)

EXPERIMENT = "H_limited_tuning"
CONFIGS = {
    "xgb_depth4": ("xgboost", {"max_depth": 4}),
    "xgb_lambda10": ("xgboost", {"reg_lambda": 10}),
    "xgb_slow200": ("xgboost", {"learning_rate": 0.05, "n_estimators": 200}),
    "cat_depth4": ("catboost", {"depth": 4}),
    "cat_l2leaf10": ("catboost", {"l2_leaf_reg": 10}),
    "cat_slow200": ("catboost", {"learning_rate": 0.05, "iterations": 200}),
}


def configured_model(code):
    name, changes = CONFIGS[code]
    model = candidate(name)
    model.set_params(**changes)
    return model


def run_one(csv_path, code, fold):
    if code not in CONFIGS or not 1 <= fold <= 5:
        raise ValueError((code, fold))
    started = time.perf_counter()
    name, changes = CONFIGS[code]
    step, kind, amount, balance, prior, label, construction = load_g_data(csv_path)
    fit_end, reserve_end, val_end = FOLDS[fold - 1]
    fit = step <= fit_end
    reserve = (step > fit_end) & (step <= reserve_end)
    validation = (step > reserve_end) & (step <= val_end)
    assert tuple((int(m.sum()), int(label[m].sum())) for m in (fit, reserve, validation)) == EXPECTED_COUNTS[fold - 1]
    assert step[fit].max() < step[reserve].min() <= step[reserve].max() < step[validation].min()
    features = RatioRecipientFeatures(name).fit(kind[fit], amount[fit], balance[fit], prior[fit])
    model = configured_model(code)

    build_start = time.perf_counter()
    x_fit = features.transform(kind[fit], amount[fit], balance[fit], step[fit], prior[fit])
    fit_build_seconds = time.perf_counter() - build_start
    fit_start = time.perf_counter()
    model.fit(x_fit, label[fit])
    fit_seconds = time.perf_counter() - fit_start
    fit_rss = psutil.Process().memory_info().rss

    build_start = time.perf_counter()
    x_reserve = features.transform(kind[reserve], amount[reserve], balance[reserve], step[reserve], prior[reserve])
    threshold_build_seconds = time.perf_counter() - build_start
    threshold_start = time.perf_counter()
    reserve_scores = scores(model, x_reserve)
    threshold, internal_f1 = choose_threshold(label[reserve], reserve_scores)
    threshold_seconds = time.perf_counter() - threshold_start
    del x_reserve, reserve_scores

    train_predict_start = time.perf_counter()
    fit_scores = scores(model, x_fit)
    fit_predict_seconds = time.perf_counter() - train_predict_start
    fit_metrics = metrics(label[fit], fit_scores, threshold)
    del x_fit, fit_scores

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
        "experiment": EXPERIMENT, "config": code, "model": name, "fold": fold,
        "parameter_changes": changes,
        "source_columns": list(SOURCE_COLUMNS), "history_source_columns": ["step", "nameDest"],
        "predictor_columns": features.columns, "label_column": "isFraud",
        "raw_step_predictor": False, "raw_account_predictor": False,
        "fit_steps": [1, fit_end], "threshold_steps": [fit_end + 1, reserve_end],
        "validation_steps": [reserve_end + 1, val_end],
        "fit_rows": int(fit.sum()), "fit_frauds": int(label[fit].sum()),
        "threshold_rows": int(reserve.sum()), "threshold_frauds": int(label[reserve].sum()),
        "fit_metrics": fit_metrics,
        "ratio_undefined_rows": {p: int((balance[m] == 0).sum()) for p, m in
                                 (("fit", fit), ("threshold", reserve), ("validation", validation))},
        "ratio_above_one_rows": {p: int((balance_share(amount[m], balance[m]) > 1).sum()) for p, m in
                                 (("fit", fit), ("threshold", reserve), ("validation", validation))},
        "history_nonzero_rows": {p: int((prior[m] > 0).sum()) for p, m in
                                 (("fit", fit), ("threshold", reserve), ("validation", validation))},
        "threshold": threshold, "threshold_f1": internal_f1,
        "fit_build_seconds": fit_build_seconds,
        "threshold_build_seconds": threshold_build_seconds,
        "validation_build_seconds": validation_build_seconds,
        "fit_seconds": fit_seconds, "threshold_seconds": threshold_seconds,
        "fit_predict_seconds": fit_predict_seconds,
        "predict_seconds": predict_seconds, "total_seconds": time.perf_counter() - started,
        "fit_rss_bytes": fit_rss, "end_rss_bytes": psutil.Process().memory_info().rss,
        "serialized_bytes": serialized.tell(), "random_seed": 42,
        "model_parameters": {k: ("NaN" if isinstance(v, float) and np.isnan(v) else v)
                             for k, v in model.get_params().items()},
        "versions": {"python": platform.python_version(), "polars": pl.__version__,
                     "numpy": np.__version__, "scikit_learn": sklearn.__version__,
                     "xgboost": xgboost.__version__, "catboost": catboost.__version__},
        **construction,
    })
    return result
