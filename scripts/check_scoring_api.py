"""Comparer quelques scores API au parcours hors ligne, sans charger de labels."""

import json
import statistics
import time
from contextlib import closing
from pathlib import Path

import numpy as np
import polars as pl

from fraud_investigation.database import open_readonly
from fraud_investigation.ml_benchmark import TYPES, scores
from fraud_investigation.scoring_service import ScoreService, ScoringPaths


def main():
    paths = ScoringPaths()
    start = time.perf_counter()
    service = ScoreService(paths)
    service.load()
    load_ms = (time.perf_counter() - start) * 1000
    # Un exemple sans historique, un second step, un solde nul et un montant nul.
    clauses = (
        "step = 1",
        "step = 2",
        "step <= 360 AND oldbalance_org IN ('0', '0.0')",
        "step <= 360 AND amount IN ('0', '0.0')",
    )
    with closing(open_readonly(paths.database)) as connection:
        selected = [connection.execute(
            f"""SELECT transaction_id, source_line_number, step, type, amount,
                       oldbalance_org, name_dest FROM transactions
                WHERE {clause} ORDER BY source_line_number LIMIT 1"""
        ).fetchone() for clause in clauses]
    if any(row is None for row in selected):
        raise RuntimeError("Échantillon de développement absent")
    selected_lines = [row["source_line_number"] for row in selected]
    csv_path = Path("data/raw/PS_20174392719_1491204439457_log.csv")
    frame = (pl.scan_csv(csv_path).with_row_index("source_line_number", offset=2)
             .filter(pl.col("source_line_number").is_in(selected_lines))
             .select("source_line_number", "step", "type", "amount",
                     "oldbalanceOrg", "nameDest").collect())
    assert frame.height == len(selected_lines)
    by_line = {row["source_line_number"]: row for row in frame.iter_rows(named=True)}
    times = {name: [] for name in ("read_and_history_ms", "features_ms", "prediction_ms")}
    for selected_row in selected:
        row = by_line[selected_row["source_line_number"]]
        assert (selected_row["step"], selected_row["type"], float(selected_row["amount"]),
                float(selected_row["oldbalance_org"]), selected_row["name_dest"]) == (
                    row["step"], row["type"], row["amount"], row["oldbalanceOrg"], row["nameDest"])
        step, dest = row["step"], row["nameDest"]
        prior = (pl.scan_csv(csv_path).filter((pl.col("step") < step)
                 & (pl.col("nameDest") == dest)).select(pl.len()).collect().item())
        kind = np.asarray([TYPES.index(row["type"])], dtype=np.uint8)
        amount = np.asarray([row["amount"]], dtype=np.float32)
        balance = np.asarray([row["oldbalanceOrg"]], dtype=np.float32)
        x = service.features.transform(kind, amount, balance,
                                       np.asarray([step], dtype=np.int16),
                                       np.asarray([prior], dtype=np.float32))
        expected = float(scores(service.model, x)[0])
        actual, measured = service.score_transaction_measured(selected_row["transaction_id"].hex())
        assert actual["suspicion_score"] == expected
        assert actual["alert"] == (expected >= service.threshold)
        assert actual["threshold"] == service.threshold
        for name in times:
            times[name].append(measured[name])
    result = {"status": "development_only_unlabeled_consistency_check",
              "sample_count": len(selected), "sample_max_step": max(row["step"] for row in frame.iter_rows(named=True)),
              "exact_score_and_decision_matches": len(selected),
              "model_load_ms": load_ms,
              "measured_ms": {name: {"min": min(values), "median": statistics.median(values),
                                     "max": max(values)} for name, values in times.items()},
              "label_files_read": False}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
