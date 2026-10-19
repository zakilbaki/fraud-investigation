"""Publier les agrégats et figures de l'expérience B face à la référence."""

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
from fraud_investigation.ml_feature_balance_org import BalanceFeatures, EXPERIMENT, MODELS


def fmt(value, digits=4):
    return "n.d." if value is None else f"{value:.{digits}f}"


def main():
    source = Path("data/ml_feature_balance_org")
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
            assert row["source_columns"] == ["step", "type", "amount", "oldbalanceOrg", "isFraud"]
            assert row["predictor_columns"] == BalanceFeatures(model).columns
            assert not set(row["predictor_columns"]) & {
                "isFraud", "isFlaggedFraud", "step", "hour_sin", "hour_cos",
                "oldbalanceDest", "newbalanceOrig", "newbalanceDest", "nameOrig", "nameDest"}
            assert row["tp"] + row["fn"] == row["frauds"]
            assert row["tn"] + row["fp"] == row["transactions"] - row["frauds"]
            assert row["alerts"] == row["tp"] + row["fp"]
            assert row["tp"] + row["fp"] + row["fn"] + row["tn"] == row["transactions"]
            assert row["precision"] == (row["tp"] / row["alerts"] if row["alerts"] else None)
            assert row["recall"] == row["tp"] / row["frauds"]
            assert abs(row["f1"] - 2 * row["tp"] / (2 * row["tp"] + row["fp"] + row["fn"])) < 1e-12
            rows.append(row)
    assert len(rows) == 20
    partial_rows = []
    for fold in range(1, 6):
        path = source / f"knn_fold_{fold}.json"
        if not path.exists():
            continue
        row = json.loads(path.read_text())
        assert statuses[f"knn_fold_{fold}"]["state"] == "ok"
        assert row["experiment"] == EXPERIMENT and row["model"] == "knn" and row["fold"] == fold
        assert row["source_columns"] == ["step", "type", "amount", "oldbalanceOrg", "isFraud"]
        assert row["predictor_columns"] == BalanceFeatures("knn").columns
        assert (row["transactions"], row["frauds"]) == EXPECTED_COUNTS[fold-1][2]
        assert row["fit_steps"] == baseline_rows["knn", fold]["fit_steps"]
        assert row["threshold_steps"] == baseline_rows["knn", fold]["threshold_steps"]
        assert row["validation_steps"] == baseline_rows["knn", fold]["validation_steps"]
        assert row["tp"] + row["fn"] == row["frauds"]
        assert row["tn"] + row["fp"] == row["transactions"] - row["frauds"]
        assert row["alerts"] == row["tp"] + row["fp"]
        partial_rows.append(row)
    assert [r["fold"] for r in partial_rows] == [1, 2, 3]
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
        for name, values in (("balance_org", current), ("baseline", previous)):
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

    output = Path("docs/results/ml_feature_balance_org.json")
    output.write_text(json.dumps({"experiment": EXPERIMENT, "baseline_source": "ml_benchmark.json",
                                  "rows": rows, "partial_knn_rows": partial_rows,
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
               label="Référence", color="#587d9a")
        ax.bar(x + .18, [np.nan if v is None else v for v in after_values], width=.36,
               label="Avec solde", color="#df9459")
        for position, value in enumerate(after_values):
            if value is None:
                ax.text(position + .18, .02, "n.d.", rotation=90, ha="center", va="bottom")
        ax.set_xticks(x, labels, rotation=35, ha="right")
        ax.set_ylim(0, 1)
        ax.set_title(title)
        ax.grid(axis="y", alpha=.2)
    axes[0].set_ylabel("Moyenne arithmétique des cinq fenêtres")
    axes[2].legend(loc="upper right")
    fig.suptitle("Expérience B : précision, rappel et F1, même échelle 0 à 1")
    fig.tight_layout()
    fig.savefig(figure_dir / "ml_feature_balance_org_means.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, len(MODELS), figsize=(15, 4), sharex=True, sharey=True)
    for ax, model in zip(axes, MODELS):
        before = [baseline_rows[model, fold]["f1"] for fold in range(1, 6)]
        after = [r["f1"] for r in rows if r["model"] == model]
        ax.plot(range(1, 6), before, marker="o", color="#587d9a", label="Référence")
        ax.plot(range(1, 6), after, marker="s", color="#df9459", label="Avec solde")
        ax.set_title(model.replace("_", " "))
        ax.set_xticks(range(1, 6))
        ax.set_ylim(0, max(.5, max(max(r["f1"] for r in rows),
                                  max(r["f1"] for r in baseline_rows.values())) * 1.05))
        ax.grid(alpha=.2)
    axes[0].set_ylabel("F1 sur validation extérieure")
    axes[-1].legend(loc="upper left")
    fig.supxlabel("Fenêtre chronologique, 1 à 5")
    fig.suptitle("Expérience B : F1 par fenêtre, échelle commune")
    fig.tight_layout()
    fig.savefig(figure_dir / "ml_feature_balance_org_windows.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, count_key, title in zip(axes, ("tp", "fp"),
                                    ("Fraudes détectées, TP", "Fausses alertes, FP")):
        before = [s[f"baseline_{count_key}_total"] for s in summary]
        after = [s[f"balance_org_{count_key}_total"] for s in summary]
        ax.barh(x - .18, before, height=.36, label="Référence", color="#587d9a")
        ax.barh(x + .18, after, height=.36, label="Avec solde", color="#df9459")
        ax.set_yticks(x, labels)
        ax.invert_yaxis()
        ax.set_title(title)
        ax.set_xlabel("Effectif cumulé sur cinq validations")
        ax.grid(axis="x", alpha=.2)
        if count_key == "fp":
            ax.set_xscale("symlog", linthresh=1)
            ax.set_xlim(left=0)
    axes[1].legend(loc="lower right")
    fig.suptitle("Expérience B : fraudes détectées et fausses alertes")
    fig.tight_layout()
    fig.savefig(figure_dir / "ml_feature_balance_org_counts.png", dpi=160)
    plt.close(fig)

    lines = ["# Lot 4.3, expérience B : solde initial de l'émetteur", "",
             "La référence utilise `type + amount`. B ajoute **uniquement `oldbalanceOrg`**. "
             "Aucune heure simulée, autre solde ou variable dérivée n'est transmise aux modèles. "
             "Les vingt scores de référence correspondants proviennent du [benchmark vérifié](ML_BENCHMARK.md), "
             "sans réentraînement. Les configurations initiales et les cinq portions temporelles sont conservées. "
             "KNN reçoit `log1p(oldbalanceOrg)` standardisé sur l'apprentissage seul ; les arbres "
             "reçoivent le solde brut. "
             "Chaque seuil est réestimé par F1 maximal sur la réserve interne, jamais sur la validation extérieure. "
             "Le test 505 à 743 n'est pas consulté. KNN a été retiré en cours de B sur décision "
             "de l'utilisateur ; ses trois fenêtres achevées restent décrites séparément ci-dessous, "
             "sans moyenne comparable.", "",
             "## Moyennes arithmétiques et changements", "",
             "Ces moyennes donnent le même poids à chacune des cinq fenêtres. Elles ne sont pas des ratios "
             "calculés sur les cases de confusion cumulées. `Δ` = avec solde moins référence ; "
             "les effectifs FP et FN sont, eux, additionnés sur les fenêtres.", "",
             "| Modèle | P réf. | P solde | ΔP | R réf. | R solde | ΔR | F1 réf. | F1 solde | ΔF1 | Alertes réf. → B | FP réf. → B | FN réf. → B |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        lines.append(f"| {s['model']} | {fmt(s['baseline_precision_mean'])} | {fmt(s['precision_mean'])} | {fmt(s['delta_precision_mean'])} | {fmt(s['baseline_recall_mean'])} | {fmt(s['recall_mean'])} | {fmt(s['delta_recall_mean'])} | {fmt(s['baseline_f1_mean'])} | {fmt(s['f1_mean'])} | {fmt(s['delta_f1_mean'])} | {s['baseline_alerts_total']:,} → {s['balance_org_alerts_total']:,} | {s['baseline_fp_total']:,} → {s['balance_org_fp_total']:,} | {s['baseline_fn_total']:,} → {s['balance_org_fn_total']:,} |")
    by_name = {s["model"]: s for s in summary}
    xgb = by_name["xgboost"]
    cat = by_name["catboost"]
    trees_fold_3 = next(r for r in rows if r["model"] == "extra_trees" and r["fold"] == 3)
    lines += ["", f"**Lecture mesurée.** XGBoost passe de F1 moyen {xgb['baseline_f1_mean']:.4f} "
              f"à {xgb['f1_mean']:.4f} ; CatBoost de {cat['baseline_f1_mean']:.4f} "
              f"à {cat['f1_mean']:.4f}. Leurs cinq fenêtres progressent chacune en F1, "
              "avec des compromis différents entre précision et rappel. "
              f"Extra Trees émet {trees_fold_3['fp']:,} fausses alertes dans la seule fenêtre 3 "
              "et son F1 y baisse malgré un meilleur F1 moyen. "
              "Ces résultats sont ceux de PaySim et ne valident pas encore le solde comme "
              "entrée d'un modèle destiné à des transactions réelles.", ""]
    lines += ["", "![Moyennes référence et expérience B](figures/ml_feature_balance_org_means.png)", "",
              "Les trois panneaux partagent une échelle verticale de 0 à 1 ; chaque barre est la moyenne "
              "d'une métrique sur cinq fenêtres. Les axes horizontaux indiquent les modèles.", "",
              "![F1 par fenêtre, référence et expérience B](figures/ml_feature_balance_org_windows.png)", "",
              "Les quatre panneaux partagent la même échelle verticale de F1. L'axe horizontal suit les "
              "validations successives. Les lignes relient des périodes différentes, pas les mêmes transactions.", "",
              "![Fraudes détectées et fausses alertes](figures/ml_feature_balance_org_counts.png)", "",
              "Chaque barre additionne les effectifs de cinq validations disjointes. L'axe TP est linéaire ; "
              "l'axe FP est logarithmique symétrique, avec une zone linéaire autour de zéro, pour garder "
              "visibles les petits et grands nombres sans masquer un éventuel zéro. Comparer les valeurs "
              "à l'intérieur de chaque panneau, car leurs axes mesurent des effectifs différents.", "",
              "## Détail par modèle et fenêtre", "",
              "P = précision ; R = rappel. Seuil et cases correspondent uniquement à l'expérience B ; "
              "les colonnes Δ comparent B à la référence sur la même validation. Une précision sans alerte "
              "serait non définie (`n.d.`).", "",
              "| Modèle | Fenêtre | Transactions | Fraudes | Seuil B | P B | R B | F1 B | ΔP | ΔR | ΔF1 | TP | FP | FN | TN | Alertes | ΔFP | ΔFN | Ajustement | Seuil | Prédiction | Total | Pic RSS |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    delta_map = {(r["model"], r["fold"]): r for r in comparisons}
    for r in rows:
        d = delta_map[r["model"], r["fold"]]
        peak = statuses[f"{r['model']}_fold_{r['fold']}"]["peak_rss_bytes"] / 2**30
        lines.append(f"| {r['model']} | {r['fold']} | {r['transactions']:,} | {r['frauds']:,} | {r['threshold']:.6g} | {fmt(r['precision'])} | {fmt(r['recall'])} | {fmt(r['f1'])} | {fmt(d['delta_precision'])} | {fmt(d['delta_recall'])} | {fmt(d['delta_f1'])} | {r['tp']:,} | {r['fp']:,} | {r['fn']:,} | {r['tn']:,} | {r['alerts']:,} | {d['delta_fp']:+,} | {d['delta_fn']:+,} | {r['fit_seconds']:.1f} s | {r['threshold_seconds']:.1f} s | {r['predict_seconds']:.1f} s | {r['total_seconds']:.1f} s | {peak:.2f} Gio |")
    lines += ["", "## KNN : trois fenêtres B historiques, comparaison incomplète", "",
              "Le calcul KNN en cours a été interrompu à la demande de l'utilisateur. Les fenêtres "
              "1 à 3 achevées restent vérifiables ; les fenêtres 4 et 5 ne sont pas évaluées. "
              "Aucune moyenne KNN sur cinq fenêtres, ni rang comparable, n'est calculée pour B. "
              "Ses résultats complets de [référence](ML_BENCHMARK.md) et de "
              "[l'expérience A](ML_FEATURE_HOUR.md) restent publiés. L'abandon concerne le "
              "coût de prédiction, le stockage et la simplicité, sans prétendre que KNN "
              "serait toujours moins performant. La taille est celle d'une sérialisation `joblib` "
              "mesurée en mémoire ; aucun modèle individuel n'est publié.", "",
              "| Fenêtre | P B | R B | F1 B | F1 référence | Seuil B | TP | FP | FN | TN | Alertes | Prédiction | Temps total | Taille sérialisée | Pic RSS |",
              "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in partial_rows:
        peak = statuses[f"knn_fold_{r['fold']}"]["peak_rss_bytes"] / 2**30
        lines.append(f"| {r['fold']} | {fmt(r['precision'])} | {fmt(r['recall'])} | {fmt(r['f1'])} | {fmt(baseline_rows['knn',r['fold']]['f1'])} | {r['threshold']:.6g} | {r['tp']:,} | {r['fp']:,} | {r['fn']:,} | {r['tn']:,} | {r['alerts']:,} | {r['predict_seconds']:.1f} s | {r['total_seconds']:.1f} s | {r['serialized_bytes']/2**20:.1f} Mio | {peak:.2f} Gio |")
    lines += ["", "## Régularité et coût local", "",
              "L'écart-type descriptif porte sur cinq F1 dépendants. Le pic RSS est échantillonné chaque "
              "seconde par l'orchestrateur et peut manquer un pic bref. Les temps additionnent les cinq "
              "exécutions ; le temps total inclut notamment cinq lectures du CSV.", "",
              "| Modèle | F1 min réf. → B | Écart-type F1 réf. → B | Ajustement réf. → B | Temps total réf. → B | Pic RSS réf. → B |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        lines.append(f"| {s['model']} | {s['baseline_f1_min']:.4f} → {s['balance_org_f1_min']:.4f} | {s['baseline_f1_std']:.4f} → {s['balance_org_f1_std']:.4f} | {s['baseline_fit_seconds_total']:.1f} → {s['balance_org_fit_seconds_total']:.1f} s | {s['baseline_total_seconds_total']:.1f} → {s['balance_org_total_seconds_total']:.1f} s | {s['baseline_peak_rss_bytes']/2**30:.2f} → {s['peak_rss_bytes']/2**30:.2f} Gio |")
    lines += ["", "## Observations mesurées", "",
              "Le tableau suivant compte les fenêtres où le F1 de B dépasse celui de la référence. "
              "Il complète la moyenne, qui peut masquer une forte dégradation sur une période. "
              "Les FP et FN sont des sommes d'effectifs, pas des moyennes de taux.", "",
              "| Modèle | Fenêtres F1 amélioré / 5 | ΔF1 moyen | ΔFP cumulés | ΔFN cumulés |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for s in summary:
        differences = [d for d in comparisons if d["model"] == s["model"]]
        lines.append(f"| {s['model']} | {sum(d['delta_f1'] > 0 for d in differences)}/5 | {fmt(s['delta_f1_mean'])} | {s['balance_org_fp_total']-s['baseline_fp_total']:+,} | {s['balance_org_fn_total']-s['baseline_fn_total']:+,} |")
    lines += ["", "## Lecture et limites", "",
              "Une hausse ou baisse est mesurée pour le **pipeline enrichi avec son seuil recalculé**. "
              "Le solde initial présente une forte signature du simulateur dans l'EDA : "
              "pour les fraudes positives CASH_OUT et TRANSFER, il coïncide fréquemment avec "
              "le montant, contrairement aux normales de ces types à la précision vérifiée. "
              "Même un gain élevé sur PaySim ne démontre pas une meilleure généralisation à "
              "des transactions réelles. Un solde supposé disponible avant l'opération doit "
              "encore être effectivement disponible dans l'application visée. Les modèles "
              "n'ont pas exactement la même représentation du montant et de `type` ; les comparaisons "
              "les plus contrôlées sont donc celles d'un même modèle avant et après ajout. Les taux de "
              "fraude des validations sont respectivement 0,0625 %, 0,0725 %, 0,0601 %, 0,1021 % "
              "et 1,3736 %. La dernière période a seulement 55 620 lignes. Les cinq résultats "
              "partagent des apprentissages et ne sont pas indépendants. Les labels du futur test "
              "avaient été vus pendant l'EDA, mais aucun score du test n'a servi ici. "
              "Le [fichier structuré](results/ml_feature_balance_org.json) garde configurations, versions, "
              "bornes, colonnes et résultats agrégés ; les journaux locaux restent hors de Git.", ""]
    Path("docs/ML_FEATURE_BALANCE_ORG.md").write_text("\n".join(lines))
    print(f"Expérience B : {len(rows)} résultats, {len(summary)} modèles complets")


if __name__ == "__main__":
    main()
