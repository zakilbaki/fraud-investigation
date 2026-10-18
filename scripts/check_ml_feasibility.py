"""Mesurer KNN et SVC sur petits échantillons, sans publier de métrique prédictive."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC

from fraud_investigation.ml_benchmark import Features, TYPES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("data/raw/PS_20174392719_1491204439457_log.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/ml_benchmark/feasibility.json"))
    args = parser.parse_args()
    frame = (pl.scan_csv(args.csv).filter(pl.col("step") <= 72)
             .select("step", "type", "amount", "isFraud").collect())
    assert frame.height == 1_030_563 and int(frame["isFraud"].sum()) == 890
    labels = frame["isFraud"].to_numpy().astype(np.uint8)
    amount = frame["amount"].to_numpy().astype(np.float32)
    kind = np.full(len(labels), 255, dtype=np.uint8)
    for code, name in enumerate(TYPES):
        kind[frame["type"].eq(name).to_numpy()] = code
    assert (kind != 255).all()
    rng = np.random.default_rng(42)
    # Les fraudes sont conservées dans l'échantillon seulement pour que SVC ait deux classes.
    # Aucun score de qualité n'est calculé ou comparé au benchmark complet.
    fraud_indices = np.flatnonzero(labels == 1)
    normal_indices = rng.permutation(np.flatnonzero(labels == 0))
    observations = []
    for size in (10_000, 20_000):
        indices = np.r_[fraud_indices[:min(50, len(fraud_indices))], normal_indices[:size - 50]]
        prep = Features("logistic").fit(kind[indices], amount[indices])
        matrix = prep.transform(kind[indices], amount[indices])
        queries = matrix[:100]
        for name, model in (("knn", KNeighborsClassifier(n_neighbors=25, n_jobs=4)),
                            ("svc_rbf", SVC(C=1, gamma="scale"))):
            start = time.perf_counter()
            model.fit(matrix, labels[indices])
            fit_seconds = time.perf_counter() - start
            start = time.perf_counter()
            model.predict(queries)
            predict_100_seconds = time.perf_counter() - start
            observations.append({"model": name, "fit_rows": size, "fit_frauds": 50,
                                 "query_rows": 100, "fit_seconds": fit_seconds,
                                 "predict_100_seconds": predict_100_seconds})
            print(observations[-1], flush=True)
    prep = Features("knn").fit(kind, amount)
    full_matrix = prep.transform(kind, amount)
    knn = KNeighborsClassifier(n_neighbors=25, n_jobs=4)
    start = time.perf_counter()
    knn.fit(full_matrix, labels)
    fit_seconds = time.perf_counter() - start
    start = time.perf_counter()
    knn.predict_proba(full_matrix[:1000])
    query_seconds = time.perf_counter() - start
    observations.append({"model": "knn", "fit_rows": len(labels),
                         "fit_frauds": int(labels.sum()), "query_rows": 1000,
                         "fit_seconds": fit_seconds, "predict_1000_seconds": query_seconds})
    print(observations[-1], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(observations, indent=2) + "\n")


if __name__ == "__main__":
    main()
