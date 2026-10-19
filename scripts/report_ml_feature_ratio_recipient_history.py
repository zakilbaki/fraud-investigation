"""Vérifier H puis publier ses comparaisons avec E et G."""

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
from fraud_investigation.ml_feature_ratio_recipient_history import (
    EXPERIMENT, MODELS, SOURCE_COLUMNS, RatioRecipientFeatures,
)

EXPECTED_SHA256 = "16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b"
METRICS = ("precision", "recall", "f1")


def fmt(value, digits=4):
    return "n.d." if value is None else f"{value:.{digits}f}"


def table(headers, records):
    return ["| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] + ["---:"] * (len(headers)-1)) + " |",
            *["| " + " | ".join(str(v) for v in record) + " |" for record in records]]


def main():
    csv_path = Path("data/raw/PS_20174392719_1491204439457_log.csv")
    with csv_path.open("rb") as file:
        source_sha256 = hashlib.file_digest(file, "sha256").hexdigest()
    assert source_sha256 == EXPECTED_SHA256
    source = Path("data/ml_feature_ratio_recipient_history")
    e_data = json.loads(Path("docs/results/ml_feature_balance_share.json").read_text())
    g_data = json.loads(Path("docs/results/ml_feature_recipient_history.json").read_text())
    coverage = json.loads(Path("docs/results/ml_recipient_history_coverage.json").read_text())
    assert e_data["source_sha256"] == g_data["source_sha256"] == coverage["source_sha256"] == source_sha256
    references = {
        "E": {(r["model"], r["fold"]): r for r in e_data["rows"]},
        "G": {(r["model"], r["fold"]): r for r in g_data["rows"]},
    }
    status = json.loads((source / "status.json").read_text())
    rows = []
    deltas = []
    for model in MODELS:
        expected_parameters = {k: ("NaN" if isinstance(v, float) and np.isnan(v) else v)
                               for k, v in candidate(model).get_params().items()}
        for fold in range(1, 6):
            key = f"{model}_fold_{fold}"
            assert status[key]["state"] == "ok"
            row = json.loads((source / f"{key}.json").read_text())
            e, g = references["E"][model, fold], references["G"][model, fold]
            assert row["experiment"] == EXPERIMENT and row["model"] == model and row["fold"] == fold
            assert row["source_columns"] == list(SOURCE_COLUMNS) == g["source_columns"]
            assert row["history_source_columns"] == g["history_source_columns"] == ["step", "nameDest"]
            assert row["predictor_columns"] == RatioRecipientFeatures(model).columns
            assert row["predictor_columns"] == [*e["predictor_columns"], "nb_entrees_anterieures"]
            assert row["predictor_columns"] == [*g["predictor_columns"][:-1], "part_solde", "nb_entrees_anterieures"]
            assert row["raw_step_predictor"] is False and row["raw_account_predictor"] is False
            assert not set(row["predictor_columns"]) & {
                "step", "nameDest", "nameOrig", "isFraud", "isFlaggedFraud",
                "oldbalanceDest", "newbalanceOrig", "newbalanceDest", "nb_sorties_anterieures"}
            a, b, c = FOLDS[fold-1]
            assert row["fit_steps"] == e["fit_steps"] == g["fit_steps"] == [1, a]
            assert row["threshold_steps"] == e["threshold_steps"] == g["threshold_steps"] == [a+1, b]
            assert row["validation_steps"] == e["validation_steps"] == g["validation_steps"] == [b+1, c]
            assert (row["fit_rows"], row["fit_frauds"]) == EXPECTED_COUNTS[fold-1][0]
            assert (row["threshold_rows"], row["threshold_frauds"]) == EXPECTED_COUNTS[fold-1][1]
            assert (row["transactions"], row["frauds"]) == EXPECTED_COUNTS[fold-1][2]
            assert row["versions"] == e["versions"] == g["versions"]
            assert row["random_seed"] == e["random_seed"] == g["random_seed"] == 42
            assert row["model_parameters"] == e["model_parameters"] == g["model_parameters"] == expected_parameters
            assert row["ratio_undefined_rows"] == e["ratio_undefined_rows"]
            assert row["ratio_above_one_rows"] == e["ratio_above_one_rows"]
            assert row["history_nonzero_rows"] == g["history_nonzero_rows"]
            for part in ("fit", "threshold", "validation"):
                assert row["history_nonzero_rows"][part] == coverage["windows"][fold-1][part]["nonzero_transactions"]
            assert np.isfinite(row["threshold"]) and 0 <= row["threshold"] <= 1
            assert all(row[field] >= 0 for field in (
                "read_seconds", "history_seconds", "fit_build_seconds", "threshold_build_seconds",
                "validation_build_seconds", "fit_seconds", "threshold_seconds", "predict_seconds", "total_seconds"))
            assert row["history_rss_after_bytes"] > 0 and status[key]["peak_rss_bytes"] > 0
            assert row["tp"] + row["fn"] == row["frauds"]
            assert row["tn"] + row["fp"] == row["transactions"] - row["frauds"]
            assert row["alerts"] == row["tp"] + row["fp"]
            assert row["precision"] == (row["tp"] / row["alerts"] if row["alerts"] else None)
            assert row["recall"] == row["tp"] / row["frauds"]
            assert abs(row["f1"] - 2*row["tp"]/(2*row["tp"]+row["fp"]+row["fn"])) < 1e-12
            rows.append(row)
            for name, prior in (("E", e), ("G", g)):
                deltas.append({"comparison": f"H_minus_{name}", "model": model, "fold": fold,
                               **{f"delta_{metric}": (row[metric]-prior[metric]
                                                      if row[metric] is not None and prior[metric] is not None else None)
                                  for metric in (*METRICS, "tp", "fp", "fn", "alerts")}})
    assert len(rows) == 10 and len(deltas) == 20
    summaries = []
    for model in MODELS:
        item = {"model": model}
        groups = {"H": [r for r in rows if r["model"] == model],
                  **{name: [references[name][model, i] for i in range(1, 6)]
                     for name in ("E", "G")}}
        for name, group in groups.items():
            for metric in METRICS:
                item[f"{name}_{metric}_mean"] = (statistics.mean(r[metric] for r in group)
                                                  if all(r[metric] is not None for r in group) else None)
            item[f"{name}_f1_min"] = min(r["f1"] for r in group)
            item[f"{name}_f1_std"] = statistics.stdev(r["f1"] for r in group)
            for field in ("tp", "fp", "fn", "tn", "alerts", "fit_seconds",
                          "threshold_seconds", "predict_seconds", "total_seconds"):
                item[f"{name}_{field}_total"] = sum(r[field] for r in group)
        for name in ("E", "G"):
            for metric in METRICS:
                h_value, prior_value = item[f"H_{metric}_mean"], item[f"{name}_{metric}_mean"]
                item[f"H_minus_{name}_{metric}_mean"] = (h_value-prior_value
                                                           if h_value is not None and prior_value is not None else None)
        item["H_history_seconds_total"] = sum(r["history_seconds"] for r in groups["H"])
        item["H_feature_build_seconds_total"] = sum(r[field] for r in groups["H"]
                                                    for field in ("fit_build_seconds", "threshold_build_seconds",
                                                                  "validation_build_seconds"))
        item["H_peak_rss_bytes"] = max(status[f"{model}_fold_{i}"]["peak_rss_bytes"] for i in range(1, 6))
        item["E_peak_rss_bytes"] = max(e_data["status"][f"{model}_fold_{i}"]["peak_rss_bytes"] for i in range(1, 6))
        item["G_peak_rss_bytes"] = max(g_data["status"][f"{model}_fold_{i}"]["peak_rss_bytes"] for i in range(1, 6))
        summaries.append(item)
    Path("docs/results/ml_feature_ratio_recipient_history.json").write_text(json.dumps({
        "experiment": EXPERIMENT, "source_sha256": source_sha256,
        "comparison_sources": ["ml_feature_balance_share.json", "ml_feature_recipient_history.json"],
        "rows": rows, "summary": summaries, "deltas": deltas, "status": status,
    }, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

    figdir = Path("docs/figures")
    labels = ["XGBoost", "CatBoost"]
    colors = {"E": "#587d9a", "G": "#7f9f78", "H": "#df9459"}
    x = np.arange(2)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    for ax, metric, title in zip(axes, METRICS, ("Précision", "Rappel", "F1")):
        for shift, name in zip((-.24, 0, .24), ("E", "G", "H")):
            ax.bar(x+shift, [s[f"{name}_{metric}_mean"] for s in summaries], .24,
                   label=name, color=colors[name])
        ax.set_xticks(x, labels)
        ax.set_ylim(0, 1)
        ax.set_title(title)
        ax.grid(axis="y", alpha=.2)
    axes[0].set_ylabel("Moyenne sur cinq validations")
    axes[-1].legend()
    fig.tight_layout()
    fig.savefig(figdir / "ml_feature_ratio_recipient_history_means.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, model, label in zip(axes, MODELS, labels):
        for name, marker in (("E", "o"), ("G", "^"), ("H", "s")):
            values = ([references[name][model, i]["f1"] for i in range(1, 6)] if name != "H"
                      else [r["f1"] for r in rows if r["model"] == model])
            ax.plot(range(1, 6), values, marker=marker, label=name, color=colors[name])
        ax.set_title(label)
        ax.set_xticks(range(1, 6))
        ax.set_ylim(0, 1)
        ax.grid(alpha=.2)
    axes[0].set_ylabel("F1 sur validation extérieure")
    axes[1].legend()
    fig.supxlabel("Fenêtre chronologique")
    fig.tight_layout()
    fig.savefig(figdir / "ml_feature_ratio_recipient_history_windows.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, field, title in zip(axes, ("tp", "fp"), ("Fraudes détectées, TP", "Fausses alertes, FP")):
        for shift, name in zip((-.24, 0, .24), ("E", "G", "H")):
            ax.barh(x+shift, [s[f"{name}_{field}_total"] for s in summaries], .24,
                    label=name, color=colors[name])
        ax.set_yticks(x, labels)
        ax.invert_yaxis()
        ax.set_title(title)
        ax.set_xlabel("Effectif cumulé sur cinq validations")
        ax.grid(axis="x", alpha=.2)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(figdir / "ml_feature_ratio_recipient_history_counts.png", dpi=160)
    plt.close(fig)

    lines = ["# Lot 4.4, expérience H : ratio et activité passée du destinataire", "",
             "H combine les cinq entrées de D, le ratio exact de [E](ML_FEATURE_BALANCE_SHARE.md) "
             "et le compteur exact de [G](ML_FEATURE_RECIPIENT_HISTORY.md), sans autre variable. "
             "Le ratio vaut `amount / oldbalanceOrg` pour un solde strictement positif, sinon `NaN` ; "
             "il n'est pas plafonné. Le compteur brut vaut le nombre de réceptions du même `nameDest` "
             "aux steps strictement antérieurs, zéro sans historique. `nameDest` ne devient pas un "
             "prédicteur brut. Le calcul ignore labels, ordre des lignes dans un step et test 505 à 743.", "",
             "Les paramètres XGBoost et CatBoost sont ceux de D, E et G. Chaque modèle apprend sur la "
             "première portion chronologique, choisit son seuil par F1 maximal sur la réserve interne, "
             "puis est évalué sur la validation extérieure. Les scores identiques sont groupés ; le "
             "seuil le plus haut départage deux maxima F1. Une précision sans alerte reste `n.d.`. "
             "E et G sont réutilisées sans réentraînement.", "",
             "## Moyennes des cinq fenêtres", "",
             "La comparaison principale est H moins E ; la comparaison complémentaire est H moins G. "
             "Chaque métrique est une moyenne arithmétique des cinq validations, non un ratio tiré "
             "des cases cumulées. `Δ` signifie H moins la référence nommée.", ""]
    mean_records = []
    for s in summaries:
        for name in ("E", "G", "H"):
            mean_records.append([s["model"], name, *[fmt(s[f"{name}_{m}_mean"]) for m in METRICS],
                                 fmt(s[f"{name}_f1_min"]), fmt(s[f"{name}_f1_std"])])
    lines += table(["Modèle", "Variante", "Précision moyenne", "Rappel moyen", "F1 moyen", "F1 min", "Écart-type F1"], mean_records)
    lines += ["", "![Métriques moyennes de E, G et H](figures/ml_feature_ratio_recipient_history_means.png)", "",
              "Axes : modèles en horizontal, moyenne des trois métriques de 0 à 1 en vertical.", "",
              "![F1 par fenêtre pour E, G et H](figures/ml_feature_ratio_recipient_history_windows.png)", "",
              "Axes : fenêtres 1 à 5 en horizontal, F1 de 0 à 1 en vertical sur une échelle commune.", "",
              "## Effectifs cumulés et écarts", "",
              "Ces nombres additionnent les cinq validations disjointes. Une baisse de FP réduit les "
              "fausses alertes ; une hausse de TP augmente les fraudes détectées.", ""]
    count_records = []
    for s in summaries:
        for name in ("E", "G", "H"):
            count_records.append([s["model"], name, *[f"{s[f'{name}_{field}_total']:,}"
                                                     for field in ("tp", "fp", "fn", "alerts")]])
        for name in ("E", "G"):
            count_records.append([s["model"], f"H − {name}",
                                  *[f"{s[f'H_{field}_total']-s[f'{name}_{field}_total']:+,}"
                                    for field in ("tp", "fp", "fn", "alerts")]])
    lines += table(["Modèle", "Variante ou écart", "TP", "FP", "FN", "Alertes"], count_records)
    lines += ["", "![Fraudes détectées et fausses alertes cumulées](figures/ml_feature_ratio_recipient_history_counts.png)", "",
              "Axes : effectifs cumulés linéaires, TP et FP dans deux panneaux distincts.", "",
              "## Résultats par fenêtre", "",
              "Chaque Δ de métrique compare H à E ou G sur la même validation et avec le seuil "
              "propre à chaque pipeline. Les seuils H et cases de confusion sont publiés ci-dessous.", ""]
    delta_map = {(d["comparison"], d["model"], d["fold"]): d for d in deltas}
    metric_records = []
    case_records = []
    cost_records = []
    for r in rows:
        de = delta_map["H_minus_E", r["model"], r["fold"]]
        dg = delta_map["H_minus_G", r["model"], r["fold"]]
        metric_records.append([r["model"], r["fold"], f"{r['threshold']:.6g}",
                               *[fmt(r[m]) for m in METRICS],
                               *[fmt(de[f"delta_{m}"]) for m in METRICS],
                               *[fmt(dg[f"delta_{m}"]) for m in METRICS]])
        case_records.append([r["model"], r["fold"], f"{r['transactions']:,}", f"{r['frauds']:,}",
                             *[f"{r[field]:,}" for field in ("alerts", "tp", "fp", "fn", "tn")],
                             f"{de['delta_tp']:+,}", f"{de['delta_fp']:+,}",
                             f"{dg['delta_tp']:+,}", f"{dg['delta_fp']:+,}"])
        build = sum(r[field] for field in ("fit_build_seconds", "threshold_build_seconds",
                                            "validation_build_seconds"))
        peak = status[f"{r['model']}_fold_{r['fold']}"]["peak_rss_bytes"]/2**30
        cost_records.append([r["model"], r["fold"], f"{r['read_seconds']:.1f}",
                             f"{r['history_seconds']:.1f}", f"{build:.1f}",
                             f"{r['fit_seconds']:.1f}", f"{r['threshold_seconds']:.1f}",
                             f"{r['predict_seconds']:.2f}", f"{r['total_seconds']:.1f}",
                             f"{r['history_rss_after_bytes']/2**30:.2f}", f"{peak:.2f}"])
    lines += table(["Modèle", "Fenêtre", "Seuil H", "P H", "R H", "F1 H",
                    "ΔP/E", "ΔR/E", "ΔF1/E", "ΔP/G", "ΔR/G", "ΔF1/G"], metric_records)
    lines += ["", "### Matrices de confusion et alertes", ""]
    lines += table(["Modèle", "Fenêtre", "Transactions", "Fraudes", "Alertes", "TP", "FP", "FN", "TN",
                    "ΔTP/E", "ΔFP/E", "ΔTP/G", "ΔFP/G"], case_records)
    lines += ["", "### Temps et mémoire observés", "",
              "Les temps sont en secondes, les mémoires en Gio. `Historique` construit le compteur "
              "sur les steps 1 à 504 ; `Variables` construit les tableaux fit, réserve et validation, "
              "ratio compris. Le RSS après historique est un instantané. Le pic RSS est échantillonné "
              "chaque seconde et peut manquer un pic très bref.", ""]
    lines += table(["Modèle", "Fenêtre", "Lecture s", "Historique s", "Variables s", "Ajustement s",
                    "Seuil s", "Prédiction s", "Total s", "RSS historique Gio", "Pic RSS Gio"], cost_records)
    lines += ["", "## Régularité et coût cumulé", "",
              "Les cinq apprentissages se recouvrent : l'écart-type est descriptif, sans inférence "
              "statistique indépendante. Chaque processus reconstruit l'historique complet, ce qui "
              "explique son addition sur cinq exécutions. Les coûts locaux de E, G et H ne sont pas "
              "des benchmarks contrôlés de vitesse, car ils ont été exécutés séparément.", ""]
    regularity = []
    for s in summaries:
        for name in ("E", "G", "H"):
            regularity.append([s["model"], name, fmt(s[f"{name}_f1_min"]), fmt(s[f"{name}_f1_std"]),
                               f"{s[f'{name}_fit_seconds_total']:.1f}",
                               f"{s[f'{name}_total_seconds_total']:.1f}",
                               f"{s[f'{name}_peak_rss_bytes']/2**30:.2f}"])
    lines += table(["Modèle", "Variante", "F1 min", "Écart-type F1", "Ajustement total s",
                    "Temps total s", "Pic RSS Gio"], regularity)
    lines += ["", "Le temps total H de construction de l'historique est "
              f"{summaries[0]['H_history_seconds_total']:.1f} s pour XGBoost et "
              f"{summaries[1]['H_history_seconds_total']:.1f} s pour CatBoost. Le temps total H de "
              "construction des tableaux de variables est "
              f"{summaries[0]['H_feature_build_seconds_total']:.1f} s et "
              f"{summaries[1]['H_feature_build_seconds_total']:.1f} s, respectivement.", "",
              "## Interprétation et limites", ""]
    for s in summaries:
        lines.append(f"Pour {s['model']}, H moins E vaut {s['H_minus_E_f1_mean']:+.4f} de F1 moyen et "
                     f"H moins G vaut {s['H_minus_G_f1_mean']:+.4f}. Ces différences décrivent les "
                     "pipelines complets avec seuil réestimé, pas un effet causal isolé.")
    lines += ["", "Face à E, H progresse en F1 sur quatre fenêtres sur cinq pour XGBoost et sur "
              "les cinq pour CatBoost. La cinquième fenêtre XGBoost baisse légèrement de 0,0013. "
              "Le gain moyen accompagné de moins de fausses alertes soutient une complémentarité "
              "pratique du compteur et du ratio dans PaySim, sans gain universel sur chaque période. "
              "Le ratio peut amplifier une signature propre au "
              "simulateur entre montant et solde initial. L'heure est simulée et la fréquence d'un "
              "destinataire ne prouve pas une intention frauduleuse. Les validations ont été réutilisées "
              "dans plusieurs expériences, les apprentissages se recouvrent et les labels du futur "
              "test avaient été examinés lors de l'EDA. Aucun score 505 à 743 n'est utilisé ici, "
              "aucun modèle final n'est retenu et aucune généralisation réelle n'est démontrée.", ""]
    Path("docs/ML_FEATURE_RATIO_RECIPIENT_HISTORY.md").write_text("\n".join(lines))
    print("Expérience H : 10 validations vérifiées, comparaisons E/G et figures produites")


if __name__ == "__main__":
    main()
