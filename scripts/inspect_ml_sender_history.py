"""Mesurer la couverture du compteur F avant tout entraînement."""

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import polars as pl
import psutil

from fraud_investigation.ml_benchmark import EXPECTED_COUNTS, FOLDS
from fraud_investigation.ml_sender_history import sender_step_history, step_coverage

EXPECTED_SHA256 = "16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b"
BUCKETS = ("count_0", "count_1", "count_2_4", "count_5_9", "count_10_plus")


def summarize(per_step, first, last):
    selected = per_step.filter(pl.col("step").is_between(first, last))
    assert selected.height == last - first + 1
    result = {
        "steps": [first, last],
        "transactions": int(selected["rows"].sum()),
        "nonzero_transactions": int(selected["nonzero_rows"].sum()),
        "sum_prior": int(selected["sum_prior"].sum()),
        "max_prior": int(selected["max_prior"].max()),
        "distribution": {key: int(selected[key].sum()) for key in BUCKETS},
    }
    assert sum(result["distribution"].values()) == result["transactions"]
    assert result["nonzero_transactions"] == result["transactions"] - result["distribution"]["count_0"]
    result["nonzero_rate"] = result["nonzero_transactions"] / result["transactions"]
    result["mean_prior"] = result["sum_prior"] / result["transactions"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path,
                        default=Path("data/raw/PS_20174392719_1491204439457_log.csv"))
    args = parser.parse_args()
    start = time.perf_counter()
    with args.csv.open("rb") as file:
        sha256 = hashlib.file_digest(file, "sha256").hexdigest()
    assert sha256 == EXPECTED_SHA256, "Empreinte CSV inattendue"
    frame = (pl.scan_csv(args.csv)
             .filter(pl.col("step") <= 504)
             .select("step", "nameOrig")
             .collect())
    assert frame.columns == ["step", "nameOrig"]
    assert frame.height == 6_064_036 and frame["step"].min() == 1 and frame["step"].max() == 504
    assert frame.null_count().to_numpy().sum() == 0
    after_read_rss = psutil.Process().memory_info().rss
    grouped = sender_step_history(frame)
    assert int(grouped["transactions"].sum()) == frame.height
    del frame
    after_group_rss = psutil.Process().memory_info().rss
    per_step = step_coverage(grouped)
    assert per_step.height == 504
    assert int(per_step["rows"].sum()) == 6_064_036
    del grouped
    overall = summarize(per_step, 1, 504)
    windows = []
    for index, (fit_end, threshold_end, validation_end) in enumerate(FOLDS, 1):
        portions = {
            "fit": summarize(per_step, 1, fit_end),
            "threshold": summarize(per_step, fit_end + 1, threshold_end),
            "validation": summarize(per_step, threshold_end + 1, validation_end),
        }
        for part, expected in zip(("fit", "threshold", "validation"), EXPECTED_COUNTS[index-1]):
            assert portions[part]["transactions"] == expected[0]
        windows.append({"fold": index, **portions})
    result = {
        "experiment": "F_sender_history_coverage_only",
        "source_sha256": sha256,
        "source_columns": ["step", "nameOrig"],
        "max_step": 504,
        "definition": "Nombre de transactions avec nameOrig égal et step strictement inférieur",
        "overall": overall,
        "windows": windows,
        "runtime": {"python": platform.python_version(), "polars": pl.__version__,
                    "seconds": time.perf_counter() - start,
                    "rss_after_read_bytes": after_read_rss,
                    "rss_after_group_bytes": after_group_rss},
    }
    output = Path("docs/results/ml_sender_history_coverage.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"overall": overall, "validation": [
        {"fold": w["fold"], **w["validation"]} for w in windows],
        "runtime": result["runtime"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
