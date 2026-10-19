"""Première comparaison PaySim, sans accès aux steps du test final."""

from __future__ import annotations

import json
import io
import os
import platform
import time
from pathlib import Path

import catboost
import joblib
import lightgbm
import numpy as np
import pandas as pd
import polars as pl
import psutil
import sklearn
import xgboost
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier


TYPES = ("CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER")
FOLDS = (
    (72, 144, 216),
    (144, 216, 288),
    (216, 288, 360),
    (288, 360, 432),
    (360, 432, 504),
)
EXPECTED_COUNTS = (
    ((1_030_563, 890), (479_034, 742), (1_288_139, 805)),
    ((1_509_597, 1_632), (1_288_139, 805), (1_160_580, 842)),
    ((2_797_736, 2_437), (1_160_580, 842), (1_227_741, 738)),
    ((3_958_316, 3_279), (1_227_741, 738), (822_359, 840)),
    ((5_186_057, 4_017), (822_359, 840), (55_620, 764)),
)
MODELS = (
    "dummy", "logistic", "sgd", "gaussian_nb", "decision_tree",
    "random_forest", "extra_trees", "hist_gradient_boosting",
    "lightgbm", "xgboost", "catboost", "mlp", "knn", "svc_rbf",
)


def load_data(csv_path: Path):
    # La projection ne donne jamais accès aux colonnes de test au benchmark.
    frame = (
        pl.scan_csv(csv_path)
        .filter(pl.col("step") <= 504)
        .select("step", "type", "amount", "isFraud")
        .collect()
    )
    assert frame.height == 6_064_036
    assert int(frame["isFraud"].sum()) == 5_621
    assert frame["step"].min() == 1 and frame["step"].max() == 504
    assert frame.null_count().to_numpy().sum() == 0
    step = frame["step"].to_numpy().astype(np.int16)
    amount = frame["amount"].to_numpy().astype(np.float32)
    label = frame["isFraud"].to_numpy().astype(np.uint8)
    assert np.isfinite(amount).all() and (amount >= 0).all()
    kind = np.full(len(step), 255, dtype=np.uint8)
    for code, name in enumerate(TYPES):
        kind[frame["type"].eq(name).to_numpy()] = code
    assert (kind != 255).all()
    return step, kind, amount, label


class Features:
    """Représentation fixe des catégories ; scaler ajusté sur l'apprentissage seul."""

    def __init__(self, name: str):
        self.name = name
        self.scaler = None

    def fit(self, kind: np.ndarray, amount: np.ndarray):
        if self.name in {"logistic", "sgd", "gaussian_nb", "mlp", "knn", "svc_rbf"}:
            self.scaler = StandardScaler().fit(np.log1p(amount).reshape(-1, 1))
        return self

    def transform(self, kind: np.ndarray, amount: np.ndarray):
        if self.name == "catboost":
            return pd.DataFrame({"type": kind.astype(np.int8), "amount": amount})
        if self.name == "dummy":
            return np.zeros((len(amount), 1), dtype=np.float32)
        one_hot = np.eye(len(TYPES), dtype=np.float32)[kind]
        if self.scaler is None:
            value = amount.reshape(-1, 1)
        else:
            value = self.scaler.transform(np.log1p(amount).reshape(-1, 1)).astype(np.float32)
        return np.column_stack((one_hot, value))


def candidate(name: str):
    common = dict(random_state=42)
    if name == "dummy":
        return DummyClassifier(strategy="prior")
    if name == "logistic":
        return LogisticRegression(solver="lbfgs", C=1, max_iter=300, **common)
    if name == "sgd":
        return SGDClassifier(loss="log_loss", alpha=1e-4, max_iter=30, tol=1e-3, **common)
    if name == "gaussian_nb":
        return GaussianNB(var_smoothing=1e-9)
    if name == "decision_tree":
        return DecisionTreeClassifier(max_depth=8, min_samples_leaf=100, **common)
    if name == "random_forest":
        return RandomForestClassifier(n_estimators=100, max_depth=12, min_samples_leaf=100, n_jobs=4, **common)
    if name == "extra_trees":
        return ExtraTreesClassifier(n_estimators=100, max_depth=12, min_samples_leaf=100, n_jobs=4, **common)
    if name == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=31, min_samples_leaf=100, early_stopping=False, **common)
    if name == "lightgbm":
        return LGBMClassifier(n_estimators=100, num_leaves=31, min_child_samples=100, learning_rate=0.1, n_jobs=4, verbosity=-1, **common)
    if name == "xgboost":
        return XGBClassifier(n_estimators=100, max_depth=6, min_child_weight=10, learning_rate=0.1, tree_method="hist", n_jobs=4, **common)
    if name == "catboost":
        return CatBoostClassifier(iterations=100, depth=6, learning_rate=0.1, loss_function="Logloss", task_type="CPU", thread_count=4, random_seed=42, allow_writing_files=False, verbose=False, cat_features=["type"])
    if name == "mlp":
        return MLPClassifier(hidden_layer_sizes=(16,), max_iter=30, **common)
    if name == "knn":
        return KNeighborsClassifier(n_neighbors=25, n_jobs=4)
    if name == "svc_rbf":
        return SVC(C=1, gamma="scale")
    raise ValueError(name)


def scores(model, x):
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(x)[:, 1], dtype=np.float64)
    return np.asarray(model.decision_function(x), dtype=np.float64)


def choose_threshold(y: np.ndarray, score: np.ndarray):
    """F1 maximum parmi scores distincts ; égalité résolue au seuil le plus haut."""
    assert len(y) == len(score) and len(y) > 0 and np.isfinite(score).all()
    order = np.argsort(-score, kind="stable")
    sorted_scores = score[order]
    sorted_y = y[order]
    last = np.r_[np.flatnonzero(np.diff(sorted_scores)), len(score) - 1]
    tp = np.cumsum(sorted_y, dtype=np.int64)[last]
    alerts = last + 1
    f1 = 2 * tp / (alerts + int(y.sum()))
    best = int(np.argmax(f1))
    return float(sorted_scores[last[best]]), float(f1[best])


def metrics(y: np.ndarray, score: np.ndarray, threshold: float):
    predicted = score >= threshold
    tp = int(np.count_nonzero(predicted & (y == 1)))
    fp = int(np.count_nonzero(predicted & (y == 0)))
    fn = int(np.count_nonzero(~predicted & (y == 1)))
    count = int(len(y))
    frauds = int(y.sum())
    tn = count - tp - fp - fn
    assert tp + fn == frauds and tn >= 0 and tn + fp == count - frauds
    return {
        "transactions": count, "frauds": frauds, "prevalence": frauds / count,
        "alerts": tp + fp, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / frauds if frauds else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0,
    }


def run_one(csv_path: Path, name: str, fold: int):
    if name not in MODELS or not 1 <= fold <= 5:
        raise ValueError((name, fold))
    total_start = time.perf_counter()
    step, kind, amount, label = load_data(csv_path)
    fit_end, threshold_end, val_end = FOLDS[fold - 1]
    fit = step <= fit_end
    reserve = (step > fit_end) & (step <= threshold_end)
    validation = (step > threshold_end) & (step <= val_end)
    assert int(fit.sum() + reserve.sum() + validation.sum()) == int((step <= val_end).sum())
    assert tuple((int(mask.sum()), int(label[mask].sum())) for mask in (fit, reserve, validation)) == EXPECTED_COUNTS[fold - 1]
    assert label[fit].min() == 0 and label[fit].max() == 1
    assert label[reserve].min() == 0 and label[reserve].max() == 1
    assert label[validation].min() == 0 and label[validation].max() == 1
    process = psutil.Process()
    prep = Features(name).fit(kind[fit], amount[fit])
    x_fit = prep.transform(kind[fit], amount[fit])
    model = candidate(name)
    fit_start = time.perf_counter()
    model.fit(x_fit, label[fit])
    fit_seconds = time.perf_counter() - fit_start
    fit_rss = process.memory_info().rss
    del x_fit
    x_reserve = prep.transform(kind[reserve], amount[reserve])
    reserve_start = time.perf_counter()
    reserve_scores = scores(model, x_reserve)
    threshold, internal_f1 = choose_threshold(label[reserve], reserve_scores)
    threshold_seconds = time.perf_counter() - reserve_start
    del x_reserve, reserve_scores
    x_validation = prep.transform(kind[validation], amount[validation])
    predict_start = time.perf_counter()
    validation_scores = scores(model, x_validation)
    predict_seconds = time.perf_counter() - predict_start
    result = metrics(label[validation], validation_scores, threshold)
    serialized = io.BytesIO()
    joblib.dump({"features": prep, "model": model}, serialized, compress=0)
    result.update({
        "model": name, "fold": fold,
        "fit_steps": [1, fit_end], "threshold_steps": [fit_end + 1, threshold_end],
        "validation_steps": [threshold_end + 1, val_end],
        "fit_rows": int(fit.sum()), "fit_frauds": int(label[fit].sum()),
        "threshold_rows": int(reserve.sum()), "threshold_frauds": int(label[reserve].sum()),
        "threshold": threshold, "threshold_f1": internal_f1,
        "fit_seconds": fit_seconds, "threshold_seconds": threshold_seconds,
        "predict_seconds": predict_seconds, "total_seconds": time.perf_counter() - total_start,
        "fit_rss_bytes": fit_rss, "end_rss_bytes": process.memory_info().rss,
        "serialized_bytes": serialized.tell(),
        "versions": {"python": platform.python_version(), "polars": pl.__version__,
                     "numpy": np.__version__, "scikit_learn": sklearn.__version__,
                     "lightgbm": lightgbm.__version__, "xgboost": xgboost.__version__,
                     "catboost": catboost.__version__},
    })
    return result


def write_result(path: Path, result: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)
