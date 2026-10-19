"""Publier les agrégats et figures de D face à B."""

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

from fraud_investigation.ml_benchmark import EXPECTED_COUNTS, FOLDS, candidate
from fraud_investigation.ml_feature_balance_org_hour import CombinedFeatures, EXPERIMENT, MODELS


def fmt(value, digits=4):
    return "n.d." if value is None else f"{value:.{digits}f}"


def main():
    source = Path("data/ml_feature_balance_org_hour")
    baseline = json.loads(Path("docs/results/ml_feature_balance_org.json").read_text())
    reference = json.loads(Path("docs/results/ml_benchmark.json").read_text())
    hour = json.loads(Path("docs/results/ml_feature_hour.json").read_text())
    destination = json.loads(Path("docs/results/ml_feature_balance_dest.json").read_text())
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
            assert row["random_seed"] == prior["random_seed"]
            assert row["model_parameters"] == prior["model_parameters"]
            initial_params = {key: ("NaN" if isinstance(value, float) and np.isnan(value) else value)
                              for key, value in candidate(model).get_params().items()}
            assert row["model_parameters"] == initial_params
            assert row["source_columns"] == ["step", "type", "amount", "oldbalanceOrg", "isFraud"]
            assert row["predictor_columns"] == CombinedFeatures(model).columns
            assert row["predictor_columns"][:-2] == prior["predictor_columns"]
            assert row["predictor_columns"][-2:] == ["hour_sin", "hour_cos"]
            assert row["raw_step_predictor"] is False
            assert np.isfinite(row["threshold"]) and 0 <= row["threshold"] <= 1
            assert all(row[key] >= 0 for key in
                       ("fit_seconds", "threshold_seconds", "predict_seconds", "total_seconds"))
            assert statuses[key]["peak_rss_bytes"] > 0
            assert not set(row["predictor_columns"]) & {
                "isFraud", "isFlaggedFraud", "step", "oldbalanceDest",
                "newbalanceOrig", "newbalanceDest", "nameOrig", "nameDest"}
            assert row["tp"] + row["fn"] == row["frauds"]
            assert row["tn"] + row["fp"] == row["transactions"] - row["frauds"]
            assert row["alerts"] == row["tp"] + row["fp"]
            assert row["tp"] + row["fp"] + row["fn"] + row["tn"] == row["transactions"]
            assert row["precision"] == (row["tp"] / row["alerts"] if row["alerts"] else None)
            assert row["recall"] == row["tp"] / row["frauds"]
            assert abs(row["f1"] - 2 * row["tp"] / (2 * row["tp"] + row["fp"] + row["fn"])) < 1e-12
            rows.append(row)
    assert len(rows) == 20
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
        for name, values in (("balance_org_hour", current), ("baseline", previous)):
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
                                "delta_tp": current_row["tp"] - prior["tp"],
                                "delta_fp": current_row["fp"] - prior["fp"],
                                "delta_fn": current_row["fn"] - prior["fn"]})

    output = Path("docs/results/ml_feature_balance_org_hour.json")
    output.write_text(json.dumps({"experiment": EXPERIMENT,
                                  "comparison_source": "ml_feature_balance_org.json",
                                  "rows": rows,
                                  "summary": summary, "deltas": comparisons,
                                  "status": statuses}, ensure_ascii=False, indent=2,
                                 allow_nan=False) + "\n")

    figure_dir = Path("docs/figures")
    labels = [m.replace("_", " ") for m in MODELS]
    x = np.arange(len(MODELS))
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
    for ax, metric, title in zip(axes, ("precision", "recall", "f1"),
                                 ("Précision", "Rappel", "F1")):
        before_values = [s[f"baseline_{metric}_mean"] for s in summary]
        after_values = [s[f"{metric}_mean"] for s in summary]
        ax.bar(x - .18, [np.nan if v is None else v for v in before_values], width=.36,
               label="B, solde émetteur", color="#587d9a")
        ax.bar(x + .18, [np.nan if v is None else v for v in after_values], width=.36,
               label="D, solde + heure", color="#df9459")
        for position, value in enumerate(after_values):
            if value is None:
                ax.text(position + .18, .02, "n.d.", rotation=90, ha="center", va="bottom")
        ax.set_xticks(x, labels, rotation=35, ha="right")
        ax.set_ylim(0, 1)
        ax.set_title(title)
        ax.grid(axis="y", alpha=.2)
    axes[0].set_ylabel("Moyenne arithmétique des cinq fenêtres")
    axes[2].legend(loc="upper right")
    fig.suptitle("Expérience D : précision, rappel et F1, même échelle 0 à 1")
    fig.tight_layout()
    fig.savefig(figure_dir / "ml_feature_balance_org_hour_means.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, len(MODELS), figsize=(15, 4), sharex=True, sharey=True)
    for ax, model in zip(axes, MODELS):
        before = [baseline_rows[model, fold]["f1"] for fold in range(1, 6)]
        after = [r["f1"] for r in rows if r["model"] == model]
        ax.plot(range(1, 6), before, marker="o", color="#587d9a", label="B, solde émetteur")
        ax.plot(range(1, 6), after, marker="s", color="#df9459", label="D, solde + heure")
        ax.set_title(model.replace("_", " "))
        ax.set_xticks(range(1, 6))
        ax.set_ylim(0, max(.5, max(max(r["f1"] for r in rows),
                                  max(r["f1"] for r in baseline_rows.values())) * 1.05))
        ax.grid(alpha=.2)
    axes[0].set_ylabel("F1 sur validation extérieure")
    axes[-1].legend(loc="upper left")
    fig.supxlabel("Fenêtre chronologique, 1 à 5")
    fig.suptitle("Expérience D : F1 par fenêtre, échelle commune")
    fig.tight_layout()
    fig.savefig(figure_dir / "ml_feature_balance_org_hour_windows.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, count_key, title in zip(axes, ("tp", "fp"),
                                    ("Fraudes détectées, TP", "Fausses alertes, FP")):
        before = [s[f"baseline_{count_key}_total"] for s in summary]
        after = [s[f"balance_org_hour_{count_key}_total"] for s in summary]
        ax.barh(x - .18, before, height=.36, label="B, solde émetteur", color="#587d9a")
        ax.barh(x + .18, after, height=.36, label="D, solde + heure", color="#df9459")
        ax.set_yticks(x, labels)
        ax.invert_yaxis()
        ax.set_title(title)
        ax.set_xlabel("Effectif cumulé sur cinq validations")
        ax.grid(axis="x", alpha=.2)
        if count_key == "fp":
            ax.set_xscale("symlog", linthresh=1)
            ax.set_xlim(left=0)
    handles, legend_labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", bbox_to_anchor=(.5, .93), ncol=2)
    fig.suptitle("Expérience D : fraudes détectées et fausses alertes", y=.99)
    fig.tight_layout(rect=(0, 0, 1, .86))
    fig.savefig(figure_dir / "ml_feature_balance_org_hour_counts.png", dpi=160)
    plt.close(fig)

    lines = ["# Lot 4.3, expérience D : solde émetteur et heure cyclique", "",
             "La comparaison principale est [B](ML_FEATURE_BALANCE_ORG.md), qui utilise `type + amount + oldbalanceOrg`. "
             "D y ajoute seulement l'heure simulée de [A](ML_FEATURE_HOUR.md), calculée par "
             "`h = (step - 1) % 24`, `sin(2πh/24)` et `cos(2πh/24)`. Les quatre modèles et leurs "
             "paramètres initiaux sont conservés. Le solde et le montant restent bruts en `float32` "
             "pour ces arbres. Le `step` brut sert au découpage et au calcul de l'heure, jamais comme "
             "prédicteur. `oldbalanceDest`, soldes après transaction, ratios, identifiants et labels "
             "n'entrent pas dans les modèles. KNN reste exclu. Les vingt résultats B vérifiés sont "
             "réutilisés sans réentraînement.", "",
             "Chaque modèle apprend sur la première portion chronologique, choisit son seuil par "
             "F1 maximal dans la réserve interne puis est évalué sur la validation extérieure. "
             "Les scores identiques sont groupés ; en cas de même F1 maximal, le seuil le plus haut "
             "est retenu. Une précision sans alerte reste non définie (`n.d.`). Le test 505 à 743 "
             "n'est pas consulté.", "",
             "## Moyennes arithmétiques : B contre D", "",
             "Chaque moyenne donne le même poids aux cinq fenêtres. Elle ne correspond pas au ratio "
             "tiré des cases de confusion cumulées. `Δ` signifie D moins B. Les effectifs TP, FP, FN "
             "et alertes sont, eux, additionnés sur les cinq validations disjointes.", "",
             "| Modèle | P B | P D | ΔP | R B | R D | ΔR | F1 B | F1 D | ΔF1 | TP B → D | FP B → D | FN B → D | Alertes B → D |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        lines.append(f"| {s['model']} | {fmt(s['baseline_precision_mean'])} | {fmt(s['precision_mean'])} | {fmt(s['delta_precision_mean'])} | {fmt(s['baseline_recall_mean'])} | {fmt(s['recall_mean'])} | {fmt(s['delta_recall_mean'])} | {fmt(s['baseline_f1_mean'])} | {fmt(s['f1_mean'])} | {fmt(s['delta_f1_mean'])} | {s['baseline_tp_total']:,} → {s['balance_org_hour_tp_total']:,} | {s['baseline_fp_total']:,} → {s['balance_org_hour_fp_total']:,} | {s['baseline_fn_total']:,} → {s['balance_org_hour_fn_total']:,} | {s['baseline_alerts_total']:,} → {s['balance_org_hour_alerts_total']:,} |")
    reference_summary = {s["model"]: s for s in reference["summary"]}
    hour_summary = {s["model"]: s for s in hour["summary"]}
    destination_summary = {s["model"]: s for s in destination["summary"]}
    lines += ["", "## F1 moyen des cinq variantes", "",
              "La référence utilise `type + amount`. A ajoute seulement l'heure, B seulement le solde "
              "émetteur, C seulement le solde destinataire. D combine B avec l'heure de A, sans C. "
              "Les paramètres et fenêtres sont identiques ; les seuils sont réestimés séparément.", "",
              "| Modèle | Référence | A | B | C | D |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        model = s["model"]
        lines.append(f"| {model} | {reference_summary[model]['f1_mean']:.4f} | "
                     f"{hour_summary[model]['f1_mean']:.4f} | "
                     f"{s['baseline_f1_mean']:.4f} | "
                     f"{destination_summary[model]['f1_mean']:.4f} | {s['f1_mean']:.4f} |")
    lines += ["", "![Précision, rappel et F1 moyens de B et D](figures/ml_feature_balance_org_hour_means.png)", "",
              "Les trois panneaux partagent l'axe vertical de 0 à 1 ; chaque barre est une moyenne "
              "sur cinq validations. L'axe horizontal nomme les modèles.", "",
              "![F1 de B et D par fenêtre](figures/ml_feature_balance_org_hour_windows.png)", "",
              "Chaque panneau suit les cinq validations dans l'ordre temporel, sur une échelle "
              "verticale commune. Les lignes relient des périodes différentes.", "",
              "![Fraudes détectées et fausses alertes de B et D](figures/ml_feature_balance_org_hour_counts.png)", "",
              "Les barres additionnent les effectifs des cinq validations. L'axe TP est linéaire ; "
              "l'axe FP est logarithmique symétrique, avec une zone linéaire près de zéro pour "
              "représenter aussi les faibles effectifs. Les deux panneaux n'ont pas la même unité "
              "de lecture sur l'axe horizontal.", "",
              "## Résultats par modèle et fenêtre", "",
              "P = précision, R = rappel. Le seuil, les cases et les temps concernent D. Les colonnes "
              "Δ comparent D à B sur la même validation. `n.d.` désigne une précision non définie.", "",
              "| Modèle | Fenêtre | Transactions | Fraudes | Seuil D | P D | R D | F1 D | ΔP | ΔR | ΔF1 | TP | FP | FN | TN | Alertes | ΔTP | ΔFP | ΔFN | Ajustement | Seuil | Prédiction | Total | Pic RSS |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    delta_map = {(r["model"], r["fold"]): r for r in comparisons}
    for r in rows:
        d = delta_map[r["model"], r["fold"]]
        peak = statuses[f"{r['model']}_fold_{r['fold']}"]["peak_rss_bytes"] / 2**30
        lines.append(f"| {r['model']} | {r['fold']} | {r['transactions']:,} | {r['frauds']:,} | {r['threshold']:.6g} | {fmt(r['precision'])} | {fmt(r['recall'])} | {fmt(r['f1'])} | {fmt(d['delta_precision'])} | {fmt(d['delta_recall'])} | {fmt(d['delta_f1'])} | {r['tp']:,} | {r['fp']:,} | {r['fn']:,} | {r['tn']:,} | {r['alerts']:,} | {d['delta_tp']:+,} | {d['delta_fp']:+,} | {d['delta_fn']:+,} | {r['fit_seconds']:.1f} s | {r['threshold_seconds']:.1f} s | {r['predict_seconds']:.1f} s | {r['total_seconds']:.1f} s | {peak:.2f} Gio |")
    lines += ["", "## Régularité et coût", "",
              "L'écart-type descriptif porte sur cinq F1 dépendants. Le pic RSS est échantillonné "
              "chaque seconde et peut manquer un pic très bref. Les temps sont additionnés sur "
              "cinq exécutions, lectures répétées du CSV comprises.", "",
              "| Modèle | F1 min B → D | Écart-type F1 B → D | F1 amélioré | Ajustement B → D | Temps total B → D | Pic RSS B → D |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        differences = [d for d in comparisons if d["model"] == s["model"]]
        lines.append(f"| {s['model']} | {s['baseline_f1_min']:.4f} → {s['balance_org_hour_f1_min']:.4f} | {s['baseline_f1_std']:.4f} → {s['balance_org_hour_f1_std']:.4f} | {sum(d['delta_f1'] > 0 for d in differences)}/5 | {s['baseline_fit_seconds_total']:.1f} → {s['balance_org_hour_fit_seconds_total']:.1f} s | {s['baseline_total_seconds_total']:.1f} → {s['balance_org_hour_total_seconds_total']:.1f} s | {s['baseline_peak_rss_bytes']/2**30:.2f} → {s['peak_rss_bytes']/2**30:.2f} Gio |")
    by_model = {s["model"]: s for s in summary}
    trees_fold_3 = next(r for r in rows if r["model"] == "extra_trees" and r["fold"] == 3)
    lines += ["", "## Observations et hypothèse de complémentarité", "",
              f"XGBoost gagne {by_model['xgboost']['delta_f1_mean']:+.4f} de F1 moyen et "
              f"CatBoost {by_model['catboost']['delta_f1_mean']:+.4f} face à B. Pour chacun, "
              "D progresse dans les cinq fenêtres ; cela soutient l'idée que l'heure simulée "
              "apporte une information supplémentaire à ces deux pipelines dans PaySim. "
              f"Random Forest varie de {by_model['random_forest']['delta_f1_mean']:+.4f} en "
              "F1 moyen, ce qui ne soutient pas le même constat pour ce modèle. "
              f"Extra Trees progresse de {by_model['extra_trees']['delta_f1_mean']:+.4f} "
              "en moyenne, mais sa troisième fenêtre conserve "
              f"{trees_fold_3['fp']:,} fausses alertes et un F1 de {trees_fold_3['f1']:.4f}. "
              "Le gain moyen ne règle donc pas son instabilité. Les temps et pics mémoire "
              "ci-dessus sont des mesures locales ; ils ne suffisent pas à attribuer chaque "
              "écart de coût aux deux coordonnées ajoutées.", ""]
    lines += ["", "## Lecture et limites", "",
              "L'écart D moins B porte sur le pipeline enrichi **et son seuil réestimé**. Il ne "
              "sépare pas l'effet des entrées de celui du seuil. L'EDA signale une forte signature "
              "du simulateur entre montant et solde initial de l'émetteur pour certaines fraudes ; "
              "un gain dans PaySim ne prouve pas une généralisation réelle. L'heure est une position "
              "simulée, sans correspondance confirmée avec une heure civile. Les cinq apprentissages "
              "se recouvrent et les validations ont déjà servi à plusieurs comparaisons ; leur "
              "moyenne n'est pas une preuve statistique indépendante. Le dernier ensemble extérieur "
              "ne contient que 55 620 lignes avec 1,3736 % de fraudes, contre 0,0601 % à 0,1021 % "
              "dans les quatre précédents. L'EDA avait exposé les labels du futur test ; aucun score "
              "des steps 505 à 743 n'est employé ici. Aucun modèle final n'est retenu. Le "
              "[fichier structuré](results/ml_feature_balance_org_hour.json) garde les versions, "
              "graines, paramètres, bornes, colonnes et agrégats. Les journaux intermédiaires "
              "restent hors de Git.", ""]
    Path("docs/ML_FEATURE_BALANCE_ORG_HOUR.md").write_text("\n".join(lines).rstrip() + "\n")
    print(f"Expérience D : {len(rows)} résultats, {len(summary)} modèles complets")


if __name__ == "__main__":
    main()
