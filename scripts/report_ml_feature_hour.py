"""Publier les agrégats et figures de l'expérience A face à la référence."""

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
import numpy as np

from fraud_investigation.ml_benchmark import EXPECTED_COUNTS, FOLDS
from fraud_investigation.ml_feature_hour import EXPERIMENT, MODELS


def fmt(value, digits=4):
    return "n.d." if value is None else f"{value:.{digits}f}"


def main():
    source = Path("data/ml_feature_hour")
    baseline = json.loads(Path("docs/results/ml_benchmark.json").read_text())
    baseline_rows = {(r["model"], r["fold"]): r for r in baseline["rows"]}
    statuses = json.loads((source / "status.json").read_text())
    rows = []
    for model in MODELS:
        for fold in range(1, 6):
            key = f"{model}_fold_{fold}"
            assert statuses[key]["state"] == "ok", key
            row = json.loads((source / f"{key}.json").read_text())
            row["model_parameters"] = {
                key: ("NaN" if isinstance(value, float) and np.isnan(value) else value)
                for key, value in row["model_parameters"].items()}
            prior = baseline_rows[model, fold]
            assert row["experiment"] == EXPERIMENT
            assert row["fit_steps"] == prior["fit_steps"] == [1, FOLDS[fold-1][0]]
            assert row["threshold_steps"] == prior["threshold_steps"]
            assert row["validation_steps"] == prior["validation_steps"]
            assert (row["fit_rows"], row["fit_frauds"]) == EXPECTED_COUNTS[fold-1][0]
            assert (row["threshold_rows"], row["threshold_frauds"]) == EXPECTED_COUNTS[fold-1][1]
            assert (row["transactions"], row["frauds"]) == EXPECTED_COUNTS[fold-1][2]
            assert row["versions"] == {k: prior["versions"][k] for k in row["versions"]}
            assert row["model_parameters"] and row["random_seed"] == 42
            assert row["source_columns"] == ["step", "type", "amount", "isFraud"]
            assert "step" not in row["predictor_columns"]
            assert not set(row["predictor_columns"]) & {
                "isFraud", "isFlaggedFraud", "oldbalanceOrg", "oldbalanceDest",
                "newbalanceOrig", "newbalanceDest", "nameOrig", "nameDest"}
            assert row["tp"] + row["fn"] == row["frauds"]
            assert row["tn"] + row["fp"] == row["transactions"] - row["frauds"]
            assert row["alerts"] == row["tp"] + row["fp"]
            assert abs(row["f1"] - 2 * row["tp"] / (2 * row["tp"] + row["fp"] + row["fn"])) < 1e-12
            rows.append(row)
    assert len(rows) == 25
    summary = []
    comparisons = []
    for model in MODELS:
        current = [r for r in rows if r["model"] == model]
        previous = [baseline_rows[model, fold] for fold in range(1, 6)]
        item = {"model": model}
        for metric in ("precision", "recall", "f1"):
            item[f"{metric}_mean"] = (statistics.mean(r[metric] for r in current)
                                       if all(r[metric] is not None for r in current) else None)
            item[f"baseline_{metric}_mean"] = (statistics.mean(r[metric] for r in previous)
                                                if all(r[metric] is not None for r in previous) else None)
            item[f"delta_{metric}_mean"] = (
                item[f"{metric}_mean"] - item[f"baseline_{metric}_mean"]
                if item[f"{metric}_mean"] is not None and item[f"baseline_{metric}_mean"] is not None else None)
        for name, values in (("hour", current), ("baseline", previous)):
            item[f"{name}_f1_min"] = min(r["f1"] for r in values)
            item[f"{name}_f1_std"] = statistics.stdev(r["f1"] for r in values)
            for key in ("alerts", "tp", "fp", "fn", "fit_seconds", "threshold_seconds",
                        "predict_seconds", "total_seconds"):
                item[f"{name}_{key}_total"] = sum(r[key] for r in values)
        item["peak_rss_bytes"] = max(statuses[f"{model}_fold_{fold}"]["peak_rss_bytes"]
                                     for fold in range(1, 6))
        item["baseline_peak_rss_bytes"] = max(
            baseline["status"][f"{model}_fold_{fold}"]["peak_rss_bytes"] for fold in range(1, 6))
        summary.append(item)
        for current_row, prior in zip(current, previous):
            comparisons.append({"model": model, "fold": current_row["fold"],
                                "delta_precision": (current_row["precision"] - prior["precision"]
                                                    if current_row["precision"] is not None and prior["precision"] is not None else None),
                                "delta_recall": current_row["recall"] - prior["recall"],
                                "delta_f1": current_row["f1"] - prior["f1"],
                                "delta_alerts": current_row["alerts"] - prior["alerts"],
                                "delta_fp": current_row["fp"] - prior["fp"],
                                "delta_fn": current_row["fn"] - prior["fn"]})

    output = Path("docs/results/ml_feature_hour.json")
    output.write_text(json.dumps({"experiment": EXPERIMENT, "baseline_source": "ml_benchmark.json",
                                  "rows": rows, "summary": summary, "deltas": comparisons,
                                  "status": statuses}, ensure_ascii=False, indent=2,
                                 allow_nan=False) + "\n")

    figure_dir = Path("docs/figures")
    labels = [m.replace("_", " ") for m in MODELS]
    x = np.arange(5)
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
    for ax, metric, title in zip(axes, ("precision", "recall", "f1"),
                                 ("Précision", "Rappel", "F1")):
        ax.bar(x - .18, [s[f"baseline_{metric}_mean"] for s in summary], width=.36,
               label="Référence", color="#587d9a")
        ax.bar(x + .18, [s[f"{metric}_mean"] for s in summary], width=.36,
               label="Avec heure", color="#df9459")
        ax.set_xticks(x, labels, rotation=35, ha="right")
        ax.set_ylim(0, 1)
        ax.set_title(title)
        ax.grid(axis="y", alpha=.2)
    axes[0].set_ylabel("Moyenne arithmétique des cinq fenêtres")
    axes[2].legend(loc="upper right")
    fig.suptitle("Expérience A : précision, rappel et F1, même échelle 0 à 1")
    fig.tight_layout()
    fig.savefig(figure_dir / "ml_feature_hour_means.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 5, figsize=(17, 4), sharex=True, sharey=True)
    for ax, model in zip(axes, MODELS):
        before = [baseline_rows[model, fold]["f1"] for fold in range(1, 6)]
        after = [r["f1"] for r in rows if r["model"] == model]
        ax.plot(range(1, 6), before, marker="o", color="#587d9a", label="Référence")
        ax.plot(range(1, 6), after, marker="s", color="#df9459", label="Avec heure")
        ax.set_title(model.replace("_", " "))
        ax.set_xticks(range(1, 6))
        ax.set_ylim(0, max(.5, max(max(r["f1"] for r in rows),
                                  max(r["f1"] for r in baseline_rows.values())) * 1.05))
        ax.grid(alpha=.2)
    axes[0].set_ylabel("F1 sur validation extérieure")
    axes[-1].legend(loc="upper left")
    fig.supxlabel("Fenêtre chronologique, 1 à 5")
    fig.suptitle("Expérience A : F1 par fenêtre, échelle commune")
    fig.tight_layout()
    fig.savefig(figure_dir / "ml_feature_hour_windows.png", dpi=160)
    plt.close(fig)

    lines = ["# Lot 4.3, expérience A : heure simulée", "",
             "La référence utilise `type + amount`. Cette expérience ajoute **une information cyclique** "
             "`h=(step-1)%24`, codée en sinus et cosinus ; ce n'est pas une heure civile confirmée. "
             "Les 25 scores de référence proviennent du [benchmark vérifié](ML_BENCHMARK.md), "
             "sans réentraînement. Les configurations initiales et les cinq portions temporelles sont conservées. "
             "Chaque seuil est réestimé par F1 maximal sur la réserve interne, jamais sur la validation extérieure. "
             "Le test 505 à 743 n'est pas consulté.", "",
             "## Moyennes arithmétiques et changements", "",
             "Ces moyennes donnent le même poids à chacune des cinq fenêtres. Elles ne sont pas des ratios "
             "calculés sur les cases de confusion cumulées. `Δ` = avec heure moins référence ; "
             "les effectifs FP et FN sont, eux, additionnés sur les fenêtres.", "",
             "| Modèle | P réf. | P heure | ΔP | R réf. | R heure | ΔR | F1 réf. | F1 heure | ΔF1 | Alertes réf. → heure | FP réf. → heure | FN réf. → heure |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        lines.append(f"| {s['model']} | {fmt(s['baseline_precision_mean'])} | {fmt(s['precision_mean'])} | {fmt(s['delta_precision_mean'])} | {fmt(s['baseline_recall_mean'])} | {fmt(s['recall_mean'])} | {fmt(s['delta_recall_mean'])} | {fmt(s['baseline_f1_mean'])} | {fmt(s['f1_mean'])} | {fmt(s['delta_f1_mean'])} | {s['baseline_alerts_total']:,} → {s['hour_alerts_total']:,} | {s['baseline_fp_total']:,} → {s['hour_fp_total']:,} | {s['baseline_fn_total']:,} → {s['hour_fn_total']:,} |")
    lines += ["", "![Moyennes référence et expérience A](figures/ml_feature_hour_means.png)", "",
              "Les trois panneaux partagent une échelle verticale de 0 à 1 ; chaque barre est la moyenne "
              "d'une métrique sur cinq fenêtres. Les axes horizontaux indiquent les modèles.", "",
              "![F1 par fenêtre, référence et expérience A](figures/ml_feature_hour_windows.png)", "",
              "Les cinq panneaux partagent la même échelle verticale de F1. L'axe horizontal suit les "
              "validations successives. Les lignes relient des périodes différentes, pas les mêmes transactions.", "",
              "## Détail par modèle et fenêtre", "",
              "P = précision ; R = rappel. Seuil et cases correspondent uniquement à l'expérience A ; "
              "les colonnes Δ comparent A à la référence sur la même validation. Une précision sans alerte "
              "serait non définie (`n.d.`).", "",
              "| Modèle | Fenêtre | Transactions | Fraudes | Seuil A | P A | R A | F1 A | ΔP | ΔR | ΔF1 | TP | FP | FN | TN | Alertes | ΔFP | ΔFN |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    delta_map = {(r["model"], r["fold"]): r for r in comparisons}
    for r in rows:
        d = delta_map[r["model"], r["fold"]]
        lines.append(f"| {r['model']} | {r['fold']} | {r['transactions']:,} | {r['frauds']:,} | {r['threshold']:.6g} | {fmt(r['precision'])} | {fmt(r['recall'])} | {fmt(r['f1'])} | {fmt(d['delta_precision'])} | {fmt(d['delta_recall'])} | {fmt(d['delta_f1'])} | {r['tp']:,} | {r['fp']:,} | {r['fn']:,} | {r['tn']:,} | {r['alerts']:,} | {d['delta_fp']:+,} | {d['delta_fn']:+,} |")
    lines += ["", "## Régularité et coût local", "",
              "L'écart-type descriptif porte sur cinq F1 dépendants. Le pic RSS est échantillonné chaque "
              "seconde par l'orchestrateur et peut manquer un pic bref. Les temps additionnent les cinq "
              "exécutions ; le temps total inclut notamment cinq lectures du CSV.", "",
              "| Modèle | F1 min réf. → A | Écart-type F1 réf. → A | Ajustement réf. → A | Temps total réf. → A | Pic RSS réf. → A |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        lines.append(f"| {s['model']} | {s['baseline_f1_min']:.4f} → {s['hour_f1_min']:.4f} | {s['baseline_f1_std']:.4f} → {s['hour_f1_std']:.4f} | {s['baseline_fit_seconds_total']:.1f} → {s['hour_fit_seconds_total']:.1f} s | {s['baseline_total_seconds_total']:.1f} → {s['hour_total_seconds_total']:.1f} s | {s['baseline_peak_rss_bytes']/2**30:.2f} → {s['peak_rss_bytes']/2**30:.2f} Gio |")
    lines += ["", "## Observations mesurées", "",
              "Le F1 moyen et le rappel moyen augmentent pour les cinq pipelines, tandis que leur "
              "précision moyenne diminue. Il s'agit d'un compromis concret : davantage de fraudes "
              "détectées, mais aussi davantage de normales alertées dans les cumuls. "
              "XGBoost et CatBoost améliorent leur F1 dans les cinq fenêtres. "
              "Extra Trees et Random Forest perdent fortement en fenêtre 3 : "
              "respectivement 8 729 et 9 418 fausses alertes dans cette seule validation, "
              "malgré un meilleur F1 moyen. KNN progresse en F1 sur les cinq fenêtres mais "
              "reste faible en fenêtre 3. Ces écarts empêchent de résumer l'expérience par "
              "un seul rang ou une seule moyenne.", "",
              "Les temps ont été mesurés dans des processus séparés sur la même machine. "
              "Le total KNN observé baisse malgré l'ajout : cette variation de temps ne "
              "démontre pas que la nouvelle variable accélère KNN ; la recherche de voisins, "
              "la charge de la machine et les prédictions peuvent changer le temps mesuré.", "",
              "## Lecture et limites", "",
              "Une hausse ou baisse est mesurée pour le **pipeline enrichi avec son seuil recalculé**. "
              "Le résultat ne prouve ni un comportement horaire réel, ni une cause métier. Les modèles "
              "n'ont pas exactement la même représentation du montant et de `type` ; les comparaisons "
              "les plus contrôlées sont donc celles d'un même modèle avant et après ajout. Les taux de "
              "fraude des validations sont respectivement 0,0625 %, 0,0725 %, 0,0601 %, 0,1021 % "
              "et 1,3736 %. La dernière période a seulement 55 620 lignes. Les cinq résultats "
              "partagent des apprentissages et ne sont pas indépendants. Les labels du futur test "
              "avaient été vus pendant l'EDA, mais aucun score du test n'a servi ici. "
              "Le [fichier structuré](results/ml_feature_hour.json) garde configurations, versions, "
              "bornes, colonnes et résultats agrégés ; les journaux locaux restent hors de Git.", ""]
    Path("docs/ML_FEATURE_HOUR.md").write_text("\n".join(lines))
    print(f"Expérience A : {len(rows)} résultats, {len(summary)} modèles complets")


if __name__ == "__main__":
    main()
