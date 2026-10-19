"""Auditer le benchmark publié et tracer sa première lecture, sans réentraîner."""

import argparse
import json
import os
import statistics
from pathlib import Path

cache = Path(".cache/matplotlib")
cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache.resolve()))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fraud_investigation.ml_benchmark import EXPECTED_COUNTS, FOLDS


SELECTED = ("xgboost", "catboost", "extra_trees", "lightgbm", "logistic")
COLORS = ("#225b91", "#b05d35", "#41865a", "#9b70ad", "#c29224")


def audit(payload):
    rows = payload["rows"]
    assert len(rows) == 65
    assert len({(r["model"], r["fold"]) for r in rows}) == 65
    assert {r["fold"] for r in rows} == set(range(1, 6))
    assert len(payload["summary"]) == 13
    for row in rows:
        fold = row["fold"] - 1
        fit_end, reserve_end, validation_end = FOLDS[fold]
        assert row["fit_steps"] == [1, fit_end]
        assert row["threshold_steps"] == [fit_end + 1, reserve_end]
        assert row["validation_steps"] == [reserve_end + 1, validation_end]
        assert (row["fit_rows"], row["fit_frauds"]) == EXPECTED_COUNTS[fold][0]
        assert (row["threshold_rows"], row["threshold_frauds"]) == EXPECTED_COUNTS[fold][1]
        assert (row["transactions"], row["frauds"]) == EXPECTED_COUNTS[fold][2]
        tp, fp, fn = (row[key] for key in ("tp", "fp", "fn"))
        tn = row["transactions"] - tp - fp - fn
        assert row["tn"] == tn and min(tp, fp, fn, tn) >= 0
        assert tp + fn == row["frauds"] and tn + fp == row["transactions"] - row["frauds"]
        assert row["alerts"] == tp + fp and row["alerts"] > 0
        assert abs(row["precision"] - tp / (tp + fp)) < 1e-12
        assert abs(row["recall"] - tp / (tp + fn)) < 1e-12
        assert abs(row["f1"] - 2 * tp / (2 * tp + fp + fn)) < 1e-12
    for item in payload["summary"]:
        group = [r for r in rows if r["model"] == item["model"]]
        assert len(group) == 5
        for metric in ("precision", "recall", "f1"):
            assert abs(item[f"{metric}_mean"] - statistics.mean(r[metric] for r in group)) < 1e-12
        assert item["fp_total"] == sum(r["fp"] for r in group)
        assert item["fn_total"] == sum(r["fn"] for r in group)
    flags_without_alert = [r["fold"] for r in payload["flag_reference"] if r["alerts"] == 0]
    assert flags_without_alert == [3, 5]
    assert all(r["precision"] is None for r in payload["flag_reference"] if r["fold"] in flags_without_alert)
    by_name = {item["model"]: item for item in payload["summary"]}
    xgb, cat = by_name["xgboost"], by_name["catboost"]
    assert payload["phase1_rule_choice"] == "xgboost"
    assert 0 <= xgb["f1_mean"] - cat["f1_mean"] < 0.005
    assert abs(xgb["f1_min"] - cat["f1_min"]) < 0.005
    assert abs(xgb["f1_std"] - cat["f1_std"]) < 0.005
    assert cat["fit_seconds_median"] > 1.2 * xgb["fit_seconds_median"]
    assert payload["svc_trial"]["minimum_elapsed_seconds_observed"] == 200
    return flags_without_alert


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("docs/results/ml_benchmark.json"))
    parser.add_argument("--figure", type=Path, default=Path("docs/figures/ml_diagnostic_five_models.png"))
    args = parser.parse_args()
    payload = json.loads(args.results.read_text())
    flags_without_alert = audit(payload)
    grouped = {name: sorted((r for r in payload["rows"] if r["model"] == name),
                            key=lambda r: r["fold"]) for name in SELECTED}
    exposure = grouped["xgboost"]
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
    for ax, metric, title, top in zip(
        axes, ("precision", "recall", "f1"),
        ("Précision : parmi les alertes, part de fraudes",
         "Rappel : parmi les fraudes, part détectée",
         "F1 : équilibre entre précision et rappel"),
        (1.0, 0.7, 0.4),
    ):
        for name, color in zip(SELECTED, COLORS):
            ax.plot(range(1, 6), [r[metric] for r in grouped[name]],
                    marker="o", linewidth=2, color=color, label=name.replace("_", " "))
        ax.set_ylabel({"precision": "Précision", "recall": "Rappel", "f1": "F1"}[metric])
        ax.set_ylim(0, top)
        ax.set_title(title, loc="left", fontsize=11)
        ax.grid(alpha=0.2)
    axes[0].legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, 1.36))
    axes[-1].set_xticks(range(1, 6), [
        f"F{r['fold']}  {r['transactions']:,} transactions\n"
        f"{r['frauds']:,} fraudes  ·  {100*r['prevalence']:.4f} %"
        for r in exposure
    ])
    axes[-1].set_xlabel("Validations extérieures dans l'ordre chronologique")
    fig.suptitle("Cinq pipelines, mêmes fenêtres ; seuil fixé avant chaque validation", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    args.figure.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.figure, dpi=160)
    plt.close(fig)
    print(f"Audit : 65 lignes, 13 moyennes, 5 fenêtres, 4 cases de confusion cohérentes ; "
          f"isFlaggedFraud sans alerte : {flags_without_alert}. Figure : {args.figure}")


if __name__ == "__main__":
    main()
