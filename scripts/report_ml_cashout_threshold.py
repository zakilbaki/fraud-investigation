"""Tracer les seuls agrégats de l'analyse exploratoire CASH_OUT."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    result = json.loads(Path("docs/results/ml_cashout_threshold_test.json").read_text())
    cash = result["cash_out"]
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2), layout="constrained")
    for ax, (key, label, color) in zip(axes, (
        ("tp", "Fraudes détectées", "#277da1"),
        ("fp", "Fausses alertes", "#e76f51"),
        ("fn", "Fraudes manquées", "#6c757d"),
    )):
        values = [cash["global"][key], cash["variant"][key]]
        bars = ax.bar(["Seuil global", "Seuil CASH_OUT"], values, color=["#b7b7b7", color])
        ax.bar_label(bars, padding=3, fontsize=10)
        ax.set_title(label)
        ax.set_ylabel("Transactions CASH_OUT")
        ax.set_ylim(0, max(values) * 1.18)
        ax.tick_params(axis="x", labelrotation=13)
    fig.suptitle("Test 505–743 : comparaison exploratoire après évaluation finale", fontsize=12)
    path = Path("docs/figures/ml_cashout_threshold_exploratory.png")
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print(path)


if __name__ == "__main__":
    main()
