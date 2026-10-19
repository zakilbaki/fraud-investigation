"""Mesurer la couverture de G avant tout entraînement et produire une figure."""

import argparse
import hashlib
import json
import os
import platform
import time
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(".cache/matplotlib").resolve()))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl
import psutil

from fraud_investigation.ml_benchmark import EXPECTED_COUNTS, FOLDS
from fraud_investigation.ml_recipient_history import (
    BUCKETS, recipient_step_coverage, recipient_step_history,
)

EXPECTED_SHA256 = "16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b"


def summarize(per_step, first, last):
    selected = per_step.filter(pl.col("step").is_between(first, last))
    assert selected.height == last - first + 1
    result = {
        "steps": [first, last],
        "transactions": int(selected["rows"].sum()),
        "nonzero_transactions": int(selected["nonzero_rows"].sum()),
        "sum_prior": int(selected["sum_prior"].sum()),
        "max_prior": int(selected["max_prior"].max()),
        "distribution": {label: int(selected[label].sum()) for label, _ in BUCKETS},
    }
    assert sum(result["distribution"].values()) == result["transactions"]
    assert result["nonzero_transactions"] == result["transactions"] - result["distribution"]["count_0"]
    result["nonzero_rate"] = result["nonzero_transactions"] / result["transactions"]
    result["mean_prior"] = result["sum_prior"] / result["transactions"]
    return result


def make_figure(overall, destination):
    distribution = overall["distribution"]
    labels = ("1", "2–4", "5–9", "10–19", "20–49", "50–99", "100–499", "500–999", "≥ 1000")
    positive = [(label, distribution[key]) for label, (key, _) in zip(labels, BUCKETS[1:])
                if distribution[key] > 0]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={"width_ratios": [1, 2]})
    left = [distribution["count_0"], overall["nonzero_transactions"]]
    bars = axes[0].bar(["0", "> 0"], [v / overall["transactions"] * 100 for v in left], color=["#587d9a", "#df9459"])
    axes[0].set_ylabel("Part des transactions (%)")
    axes[0].set_title("Historique absent ou présent")
    axes[0].set_ylim(0, 105)
    for bar, count in zip(bars, left):
        axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f"{count:,}".replace(",", " "),
                     ha="center", va="bottom", fontsize=9)
    axes[1].bar([label for label, _ in positive], [value for _, value in positive], color="#df9459")
    axes[1].set_yscale("log")
    axes[1].set_ylabel("Transactions (échelle logarithmique)")
    axes[1].set_xlabel("Nombre de réceptions aux steps antérieurs")
    axes[1].set_title("Distribution des compteurs non nuls")
    axes[1].tick_params(axis="x", rotation=35)
    axes[1].grid(axis="y", alpha=.25)
    fig.suptitle("Expérience G : couverture du compteur destinataire, steps 1 à 504")
    fig.tight_layout()
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path,
                        default=Path("data/raw/PS_20174392719_1491204439457_log.csv"))
    args = parser.parse_args()
    start = time.perf_counter()
    with args.csv.open("rb") as file:
        sha256 = hashlib.file_digest(file, "sha256").hexdigest()
    assert sha256 == EXPECTED_SHA256
    frame = (pl.scan_csv(args.csv)
             .filter(pl.col("step") <= 504)
             .select("step", "nameDest")
             .collect())
    assert frame.columns == ["step", "nameDest"]
    assert frame.height == 6_064_036 and frame["step"].min() == 1 and frame["step"].max() == 504
    assert frame.null_count().to_numpy().sum() == 0
    read_rss = psutil.Process().memory_info().rss
    grouped = recipient_step_history(frame)
    assert int(grouped["transactions"].sum()) == frame.height
    del frame
    grouped_rss = psutil.Process().memory_info().rss
    per_step = recipient_step_coverage(grouped)
    assert per_step.height == 504 and int(per_step["rows"].sum()) == 6_064_036
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
        "experiment": "G_recipient_history_coverage_only",
        "source_sha256": sha256,
        "source_columns": ["step", "nameDest"],
        "max_step": 504,
        "definition": "Nombre de transactions avec nameDest égal et step strictement inférieur",
        "overall": overall,
        "windows": windows,
        "runtime": {"python": platform.python_version(), "polars": pl.__version__,
                    "matplotlib": matplotlib.__version__,
                    "seconds": time.perf_counter() - start,
                    "rss_after_read_bytes": read_rss,
                    "rss_after_group_bytes": grouped_rss},
    }
    Path("docs/results/ml_recipient_history_coverage.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    make_figure(overall, Path("docs/figures/ml_recipient_history_distribution.png"))
    print(json.dumps({"overall": overall, "validation": [
        {"fold": w["fold"], **w["validation"]} for w in windows],
        "runtime": result["runtime"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
