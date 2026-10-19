"""Vérifier les résultats E et publier la comparaison agrégée avec D."""

import hashlib
import json
import os
import statistics
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(".cache/matplotlib").resolve()))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fraud_investigation.ml_benchmark import EXPECTED_COUNTS, FOLDS, candidate
from fraud_investigation.ml_feature_balance_share import EXPERIMENT, MODELS, ShareFeatures


def show(value):
    return "n.d." if value is None else f"{value:.4f}"


def main():
    csv_path = Path("data/raw/PS_20174392719_1491204439457_log.csv")
    with csv_path.open("rb") as csv_file:
        source_sha256 = hashlib.file_digest(csv_file, "sha256").hexdigest()
    assert source_sha256 == "16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b"
    local = Path("data/ml_feature_balance_share")
    source = json.loads(Path("docs/results/ml_feature_balance_org_hour.json").read_text())
    previous = {(r["model"], r["fold"]): r for r in source["rows"]}
    status = json.loads((local / "status.json").read_text())
    rows = []
    deltas = []
    for model in MODELS:
        for fold in range(1, 6):
            key = f"{model}_fold_{fold}"
            assert status[key]["state"] == "ok"
            r = json.loads((local / f"{key}.json").read_text())
            d = previous[model, fold]
            assert r["experiment"] == EXPERIMENT and r["model"] == model and r["fold"] == fold
            assert r["source_columns"] == ["step", "type", "amount", "oldbalanceOrg", "isFraud"]
            assert r["predictor_columns"] == ShareFeatures(model).columns
            assert r["predictor_columns"] == [*d["predictor_columns"], "part_solde"]
            assert r["raw_step_predictor"] is False
            assert r["fit_steps"] == d["fit_steps"] == [1, FOLDS[fold-1][0]]
            assert r["threshold_steps"] == d["threshold_steps"] == [FOLDS[fold-1][0]+1, FOLDS[fold-1][1]]
            assert r["validation_steps"] == d["validation_steps"] == [FOLDS[fold-1][1]+1, FOLDS[fold-1][2]]
            assert (r["fit_rows"], r["fit_frauds"]) == EXPECTED_COUNTS[fold-1][0]
            assert (r["threshold_rows"], r["threshold_frauds"]) == EXPECTED_COUNTS[fold-1][1]
            assert (r["transactions"], r["frauds"]) == EXPECTED_COUNTS[fold-1][2]
            assert r["versions"] == d["versions"] and r["random_seed"] == d["random_seed"] == 42
            assert r["model_parameters"] == d["model_parameters"]
            assert r["model_parameters"] == {k: ("NaN" if isinstance(v, float) and np.isnan(v) else v)
                                              for k, v in candidate(model).get_params().items()}
            assert not set(r["predictor_columns"]) & {"step", "isFraud", "isFlaggedFraud", "nameOrig", "nameDest",
                                                       "oldbalanceDest", "newbalanceOrig", "newbalanceDest"}
            assert r["tp"] + r["fn"] == r["frauds"]
            assert r["tn"] + r["fp"] == r["transactions"] - r["frauds"]
            assert r["alerts"] == r["tp"] + r["fp"]
            assert r["precision"] == (r["tp"] / r["alerts"] if r["alerts"] else None)
            assert r["recall"] == r["tp"] / r["frauds"]
            assert abs(r["f1"] - 2*r["tp"] / (2*r["tp"] + r["fp"] + r["fn"])) < 1e-12
            assert all(0 <= r["ratio_undefined_rows"][part] <= count[0]
                       for part, count in zip(("fit", "threshold", "validation"), EXPECTED_COUNTS[fold-1]))
            assert all(0 <= r["ratio_above_one_rows"][part] <= count[0]
                       for part, count in zip(("fit", "threshold", "validation"), EXPECTED_COUNTS[fold-1]))
            assert status[key]["peak_rss_bytes"] > 0
            rows.append(r)
            deltas.append({"model": model, "fold": fold,
                           **{f"delta_{m}": (r[m]-d[m] if r[m] is not None and d[m] is not None else None)
                              for m in ("precision", "recall", "f1", "tp", "fp", "fn", "alerts")}})
    summary = []
    for model in MODELS:
        e = [r for r in rows if r["model"] == model]
        d = [previous[model, fold] for fold in range(1, 6)]
        item = {"model": model}
        for metric in ("precision", "recall", "f1"):
            item[f"e_{metric}_mean"] = statistics.mean(r[metric] for r in e) if all(r[metric] is not None for r in e) else None
            item[f"d_{metric}_mean"] = statistics.mean(r[metric] for r in d) if all(r[metric] is not None for r in d) else None
            item[f"delta_{metric}_mean"] = (item[f"e_{metric}_mean"]-item[f"d_{metric}_mean"]
                                           if item[f"e_{metric}_mean"] is not None and item[f"d_{metric}_mean"] is not None else None)
        for tag, group in (("e", e), ("d", d)):
            item[f"{tag}_f1_min"] = min(r["f1"] for r in group)
            item[f"{tag}_f1_std"] = statistics.stdev(r["f1"] for r in group)
            for field in ("tp", "fp", "fn", "tn", "alerts", "fit_seconds", "threshold_seconds", "predict_seconds", "total_seconds"):
                item[f"{tag}_{field}_total"] = sum(r[field] for r in group)
        item["e_peak_rss_bytes"] = max(status[f"{model}_fold_{i}"]["peak_rss_bytes"] for i in range(1, 6))
        item["d_peak_rss_bytes"] = max(source["status"][f"{model}_fold_{i}"]["peak_rss_bytes"] for i in range(1, 6))
        summary.append(item)
    assert len(rows) == 10
    Path("docs/results/ml_feature_balance_share.json").write_text(json.dumps({
        "experiment": EXPERIMENT, "source_sha256": source_sha256,
        "comparison_source": "ml_feature_balance_org_hour.json",
        "rows": rows, "summary": summary, "deltas": deltas, "status": status,
    }, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

    figdir = Path("docs/figures")
    names = ["XGBoost", "CatBoost"]
    x = np.arange(2)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
    for ax, metric, title in zip(axes, ("precision", "recall", "f1"), ("Précision", "Rappel", "F1")):
        ax.bar(x-.18, [s[f"d_{metric}_mean"] for s in summary], .36, label="D", color="#587d9a")
        ax.bar(x+.18, [s[f"e_{metric}_mean"] for s in summary], .36, label="E", color="#df9459")
        ax.set_xticks(x, names)
        ax.set_ylim(0, 1)
        ax.set_title(title)
        ax.grid(axis="y", alpha=.2)
    axes[0].set_ylabel("Moyenne sur cinq validations")
    axes[-1].legend()
    fig.tight_layout()
    fig.savefig(figdir / "ml_feature_balance_share_means.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, model, name in zip(axes, MODELS, names):
        ax.plot(range(1, 6), [previous[model, i]["f1"] for i in range(1, 6)], marker="o", label="D", color="#587d9a")
        ax.plot(range(1, 6), [r["f1"] for r in rows if r["model"] == model], marker="s", label="E", color="#df9459")
        ax.set_title(name)
        ax.set_xticks(range(1, 6))
        ax.set_ylim(0, 1)
        ax.grid(alpha=.2)
    axes[0].set_ylabel("F1 sur validation extérieure")
    axes[1].legend()
    fig.supxlabel("Fenêtre chronologique")
    fig.tight_layout()
    fig.savefig(figdir / "ml_feature_balance_share_windows.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, field, title in zip(axes, ("tp", "fp"), ("Fraudes détectées, TP", "Fausses alertes, FP")):
        ax.barh(x-.18, [s[f"d_{field}_total"] for s in summary], .36, label="D", color="#587d9a")
        ax.barh(x+.18, [s[f"e_{field}_total"] for s in summary], .36, label="E", color="#df9459")
        ax.set_yticks(x, names)
        ax.invert_yaxis()
        ax.set_title(title)
        ax.set_xlabel("Effectif cumulé sur cinq validations")
        ax.grid(axis="x", alpha=.2)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(figdir / "ml_feature_balance_share_counts.png", dpi=160)
    plt.close(fig)

    lines = ["# Lot 4.4, expérience E : part du solde initial utilisée", "",
             "D utilise `type + amount + oldbalanceOrg + hour_sin + hour_cos`. E ajoute seulement "
             "`part_solde = amount / oldbalanceOrg` lorsque le solde est strictement positif. "
             "Un solde nul donne `NaN`, traité nativement par XGBoost et CatBoost, sans imputation. "
             "Les ratios supérieurs à 1 ne sont pas plafonnés. Les modèles, paramètres, graines, "
             "fenêtres et seuils internes restent ceux de D. Le test 505 à 743 n'est pas consulté.", "",
             "Chaque moyenne ci-dessous est arithmétique sur cinq fenêtres. Les effectifs sont cumulés "
             "sur cinq validations disjointes ; ils ne donnent pas la moyenne des métriques.", "",
             "## Moyennes et effectifs cumulés", "",
             "| Modèle | P D | P E | ΔP | R D | R E | ΔR | F1 D | F1 E | ΔF1 | TP D → E | FP D → E | FN D → E | Alertes D → E |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        lines.append(f"| {s['model']} | {show(s['d_precision_mean'])} | {show(s['e_precision_mean'])} | {show(s['delta_precision_mean'])} | {show(s['d_recall_mean'])} | {show(s['e_recall_mean'])} | {show(s['delta_recall_mean'])} | {show(s['d_f1_mean'])} | {show(s['e_f1_mean'])} | {show(s['delta_f1_mean'])} | {s['d_tp_total']:,} → {s['e_tp_total']:,} | {s['d_fp_total']:,} → {s['e_fp_total']:,} | {s['d_fn_total']:,} → {s['e_fn_total']:,} | {s['d_alerts_total']:,} → {s['e_alerts_total']:,} |")
    lines += ["", "![Moyennes D et E](figures/ml_feature_balance_share_means.png)", "",
              "Axes : modèles en horizontal, moyenne des métriques de 0 à 1 en vertical.", "",
              "![F1 par fenêtre](figures/ml_feature_balance_share_windows.png)", "",
              "Axes : fenêtres 1 à 5 en horizontal, F1 de 0 à 1 en vertical, même échelle pour les deux modèles.", "",
              "![TP et FP cumulés](figures/ml_feature_balance_share_counts.png)", "",
              "Axes : effectifs cumulés, échelle linéaire, séparés entre fraudes détectées et fausses alertes.", "",
              "## Résultats par fenêtre", "",
              "La précision sans alerte serait notée `n.d.`. Le seuil est choisi par F1 maximal dans la réserve interne, "
              "avec regroupement des scores identiques et choix du seuil le plus élevé en cas d'égalité.", "",
              "| Modèle | Fenêtre | Transactions | Fraudes | Seuil E | P E | R E | F1 E | ΔP | ΔR | ΔF1 | TP | FP | FN | TN | Alertes | Ajustement | Seuil | Prédiction | Total | Pic RSS | Ratio manquant en validation | Ratio > 1 en validation |",
              "| " + " | ".join(["---"] + ["---:"] * 22) + " |"]
    dm = {(d["model"], d["fold"]): d for d in deltas}
    for r in rows:
        peak = status[f"{r['model']}_fold_{r['fold']}"]["peak_rss_bytes"] / 2**30
        lines.append(f"| {r['model']} | {r['fold']} | {r['transactions']:,} | {r['frauds']:,} | {r['threshold']:.6g} | {show(r['precision'])} | {show(r['recall'])} | {show(r['f1'])} | {show(dm[r['model'],r['fold']]['delta_precision'])} | {show(dm[r['model'],r['fold']]['delta_recall'])} | {show(dm[r['model'],r['fold']]['delta_f1'])} | {r['tp']:,} | {r['fp']:,} | {r['fn']:,} | {r['tn']:,} | {r['alerts']:,} | {r['fit_seconds']:.1f} s | {r['threshold_seconds']:.1f} s | {r['predict_seconds']:.1f} s | {r['total_seconds']:.1f} s | {peak:.2f} Gio | {r['ratio_undefined_rows']['validation']:,} | {r['ratio_above_one_rows']['validation']:,} |")
    lines += ["", "## Régularité, coût et interprétation", "",
              "| Modèle | F1 minimum D → E | Écart-type descriptif D → E | Ajustement D → E | Temps total D → E | Pic RSS D → E |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        lines.append(f"| {s['model']} | {s['d_f1_min']:.4f} → {s['e_f1_min']:.4f} | {s['d_f1_std']:.4f} → {s['e_f1_std']:.4f} | {s['d_fit_seconds_total']:.1f} → {s['e_fit_seconds_total']:.1f} s | {s['d_total_seconds_total']:.1f} → {s['e_total_seconds_total']:.1f} s | {s['d_peak_rss_bytes']/2**30:.2f} → {s['e_peak_rss_bytes']/2**30:.2f} Gio |")
    lines += ["", "Le ratio rend explicite une relation entre deux entrées déjà présentes. Une différence "
              "mesurée décrit le pipeline E et son seuil réestimé, pas un effet causal isolé de la variable. "
              "La relation montant et solde initial porte une signature forte du simulateur PaySim ; "
              "un gain éventuel ne garantit pas une généralisation à des opérations réelles. "
              "L'heure est simulée. Les apprentissages se recouvrent, les validations ont déjà guidé "
              "plusieurs analyses et les labels du futur test ont été exposés pendant l'EDA. "
              "Aucun modèle final n'est annoncé. Les résultats structurés gardent les paramètres, "
              "versions, bornes, colonnes et compteurs de ratios manquants ou supérieurs à 1.", ""]
    Path("docs/ML_FEATURE_BALANCE_SHARE.md").write_text("\n".join(lines))
    print("Expérience E : 10 validations vérifiées, rapport et figures produits")


if __name__ == "__main__":
    main()
