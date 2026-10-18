"""Publier les résultats agrégés des cinq fenêtres, sans données individuelles."""

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
import numpy as np
import polars as pl

from fraud_investigation.ml_benchmark import FOLDS, MODELS, metrics


SIMPLICITY = (
    "dummy", "gaussian_nb", "logistic", "sgd", "decision_tree",
    "hist_gradient_boosting", "extra_trees", "random_forest", "lightgbm",
    "xgboost", "catboost", "mlp", "knn", "svc_rbf",
)


def selection(summary):
    """Appliquer les départages préannoncés, sans arrondir les métriques."""
    if not summary:
        return None, []
    trace = []
    best = max(item["f1_mean"] for item in summary)
    candidates = [item for item in summary if best - item["f1_mean"] < 0.005]
    trace.append(f"F1 moyen à moins de 0,005 du meilleur : {', '.join(i['model'] for i in candidates)}")
    minimum = max(item["f1_min"] for item in candidates)
    candidates = [item for item in candidates if minimum - item["f1_min"] < 0.005]
    trace.append(f"F1 minimum à moins de 0,005 du meilleur : {', '.join(i['model'] for i in candidates)}")
    dispersion = min(item["f1_std"] for item in candidates)
    candidates = [item for item in candidates if item["f1_std"] - dispersion < 0.005]
    trace.append(f"Écart-type à moins de 0,005 du meilleur : {', '.join(i['model'] for i in candidates)}")
    fastest = min(item["fit_seconds_median"] for item in candidates)
    candidates = [item for item in candidates if item["fit_seconds_median"] <= fastest * 1.2]
    trace.append(f"Temps médian à moins de 20 % du plus court : {', '.join(i['model'] for i in candidates)}")
    smallest = min(item["model_size_bytes_fold_5"] for item in candidates)
    candidates = [item for item in candidates if item["model_size_bytes_fold_5"] <= smallest * 1.2]
    trace.append(f"Taille à moins de 20 % de la plus petite : {', '.join(i['model'] for i in candidates)}")
    winner = min(candidates, key=lambda i: (SIMPLICITY.index(i["model"]), i["model"]))
    return winner["model"], trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/ml_benchmark"))
    parser.add_argument("--csv", type=Path, default=Path("data/raw/PS_20174392719_1491204439457_log.csv"))
    parser.add_argument("--report", type=Path, default=Path("docs/ML_BENCHMARK.md"))
    args = parser.parse_args()
    rows = []
    for name in MODELS:
        for fold in range(1, 6):
            path = args.input / f"{name}_fold_{fold}.json"
            if path.exists():
                rows.append(json.loads(path.read_text()))
    if not rows:
        raise SystemExit("Aucun résultat complet disponible")
    status_path = args.input / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    svc_path = args.input / "svc_feasibility.json"
    svc_trial = json.loads(svc_path.read_text()) if svc_path.exists() else None
    feasibility_path = args.input / "feasibility.json"
    feasibility = json.loads(feasibility_path.read_text()) if feasibility_path.exists() else []
    by_model = {name: [r for r in rows if r["model"] == name] for name in MODELS}
    complete = {name: values for name, values in by_model.items() if len(values) == 5}
    summary = []
    for name, values in complete.items():
        values.sort(key=lambda r: r["fold"])
        summary.append({
            "model": name,
            "precision_mean": statistics.mean(r["precision"] for r in values),
            "recall_mean": statistics.mean(r["recall"] for r in values),
            "f1_mean": statistics.mean(r["f1"] for r in values),
            "f1_min": min(r["f1"] for r in values),
            "f1_std": statistics.stdev(r["f1"] for r in values),
            "fit_seconds_median": statistics.median(r["fit_seconds"] for r in values),
            "fit_seconds_total": sum(r["fit_seconds"] for r in values),
            "predict_seconds_total": sum(r["predict_seconds"] for r in values),
            "alert_total": sum(r["alerts"] for r in values),
            "fp_total": sum(r["fp"] for r in values),
            "fn_total": sum(r["fn"] for r in values),
            "model_size_bytes_fold_5": values[-1]["serialized_bytes"],
            "peak_rss_bytes": max(status.get(f"{name}_fold_{r['fold']}", {}).get("peak_rss_bytes", 0) for r in values),
        })
    summary.sort(key=lambda r: -r["f1_mean"])
    winner, trace = selection(summary)
    flag_frame = (pl.scan_csv(args.csv)
                  .filter(pl.col("step") <= 504)
                  .select("step", "isFraud", "isFlaggedFraud")
                  .collect())
    assert flag_frame.height == 6_064_036 and int(flag_frame["isFraud"].sum()) == 5_621
    flag_rows = []
    for fold, (_, previous_end, validation_end) in enumerate(FOLDS, 1):
        part = flag_frame.filter((pl.col("step") > previous_end) & (pl.col("step") <= validation_end))
        one = metrics(part["isFraud"].to_numpy(), part["isFlaggedFraud"].to_numpy(), 1)
        one["fold"] = fold
        flag_rows.append(one)
    payload = {"rows": rows, "summary": summary, "phase1_rule_choice": winner,
               "selection_trace": trace, "flag_reference": flag_rows, "status": status,
               "feasibility": feasibility, "svc_trial": svc_trial}
    result_path = Path("docs/results/ml_benchmark.json")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    figures = Path("docs/figures")
    figures.mkdir(exist_ok=True)
    if summary:
        labels = [r["model"].replace("_", " ") for r in summary]
        positions = np.arange(len(labels))
        fig, axes = plt.subplots(1, 3, figsize=(15, max(5, len(labels) * 0.45)), sharey=True)
        for ax, key, title, color, xmax in zip(
            axes, ("precision_mean", "recall_mean", "f1_mean"),
            ("Précision", "Rappel", "F1"), ("#2a6f9e", "#de8733", "#398657"),
            (1, 1, max(0.35, max(r["f1_mean"] for r in summary) * 1.1)),
        ):
            ax.barh(positions, [r[key] for r in summary], color=color)
            ax.set_yticks(positions, labels)
            ax.set_xlim(0, xmax)
            ax.set_title(title)
            ax.set_xlabel("Moyenne des cinq fenêtres")
            ax.grid(axis="x", alpha=0.15)
        axes[0].invert_yaxis()
        fig.suptitle("Comparaison des modèles, seuil choisi dans chaque train")
        fig.tight_layout()
        fig.savefig(figures / "ml_model_means.png", dpi=160)
        plt.close(fig)

        columns = 3
        count = len(summary)
        fig, axes = plt.subplots((count + columns - 1) // columns, columns,
                                 figsize=(14, 3 * ((count + columns - 1) // columns)),
                                 sharex=True, sharey=True)
        flat = np.ravel(axes)
        for ax, item in zip(flat, summary):
            values = complete[item["model"]]
            ax.plot([r["fold"] for r in values], [r["f1"] for r in values],
                    color="#266ba0", marker="o", linewidth=2)
            ax.set_title(item["model"].replace("_", " "))
            ax.set_xticks(range(1, 6))
            ax.set_ylim(0, max(0.35, max(r["f1"] for r in rows) * 1.05))
            ax.grid(alpha=0.2)
        for ax in flat[count:]:
            ax.set_visible(False)
        fig.supxlabel("Fenêtre extérieure 1 à 5")
        fig.supylabel("F1 sur validation extérieure")
        fig.suptitle("Évolution du F1 par modèle ; prévalences 0,062 %, 0,073 %, 0,060 %, 0,102 %, 1,374 %")
        fig.tight_layout()
        fig.savefig(figures / "ml_model_windows.png", dpi=160)
        plt.close(fig)

    lines = [
        "# Lot 4.2 : première comparaison des modèles PaySim", "",
        "Les métriques proviennent exclusivement des validations extérieures 145 à 504. "
        "Le test 505 à 743 n'a pas été lu pour la comparaison. Chaque seuil maximise le F1 "
        "sur la réserve chronologique interne du train, avant le calcul des métriques extérieures. "
        "Le [protocole](ML_PROTOCOL.md) fixe les bornes et les règles de sélection.", "",
        "## Moyennes sur les cinq fenêtres", "",
        "Les moyennes ci-dessous sont arithmétiques et non pondérées. Les modèles incomplets n'y figurent pas.", "",
        "| Modèle | Précision | Rappel | F1 | F1 minimum | Écart-type F1 | Temps médian d'ajustement | FP cumulés | FN cumulés |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in summary:
        lines.append(f"| {r['model']} | {r['precision_mean']:.4f} | {r['recall_mean']:.4f} | {r['f1_mean']:.4f} | {r['f1_min']:.4f} | {r['f1_std']:.4f} | {r['fit_seconds_median']:.1f} s | {r['fp_total']:,} | {r['fn_total']:,} |")
    lines += ["", f"**Choix provisoire selon la règle préannoncée de phase 1 : `{winner}`.** "
              "Il ne clôt pas l'analyse des résultats ni les expériences d'approfondissement.", ""]
    lines += [f"- {item}" for item in trace]
    lines += ["", "![Moyennes des métriques](figures/ml_model_means.png)", "",
              "La figure des moyennes a un axe horizontal propre à chaque métrique. "
              "Le F1 est agrandi pour rendre lisibles ses écarts ; il ne faut pas comparer la longueur "
              "d'une barre entre panneaux sans lire l'échelle.", "",
              "![F1 par fenêtre](figures/ml_model_windows.png)", "",
              "Les petits panneaux utilisent la même échelle de F1. Les numéros 1 à 5 suivent "
              "l'ordre chronologique ; leurs prévalences sont indiquées dans le titre.", "",
              "## Détail par modèle et fenêtre", "",
              "`P` = précision, `R` = rappel. `FP` = normales alertées ; `FN` = fraudes manquées. "
              "La précision est reportée à 0 par convention si aucune alerte n'est émise.", "",
              "| Modèle | Fenêtre | Transactions | Fraudes | Prévalence | Seuil interne | P | R | F1 | Alertes | FP | FN | Ajustement | Choix du seuil | Prédiction | Total |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name in MODELS:
        for r in sorted(by_model[name], key=lambda x: x["fold"]):
            lines.append(f"| {name} | {r['fold']} | {r['transactions']:,} | {r['frauds']:,} | {r['prevalence']*100:.3f} % | {r['threshold']:.6g} | {r['precision']:.4f} | {r['recall']:.4f} | {r['f1']:.4f} | {r['alerts']:,} | {r['fp']:,} | {r['fn']:,} | {r['fit_seconds']:.1f} s | {r['threshold_seconds']:.1f} s | {r['predict_seconds']:.1f} s | {r['total_seconds']:.1f} s |")
    lines += ["", "## Référence PaySim `isFlaggedFraud`", "",
              "Cette règle fournie par le simulateur n'est jamais une entrée des modèles ni un candidat à sélectionner. "
              "Elle est évaluée directement sur les mêmes validations extérieures, sans seuil ajusté.", "",
              "| Fenêtre | Précision | Rappel | F1 | Alertes | FP | FN |",
              "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in flag_rows:
        lines.append(f"| {r['fold']} | {r['precision']:.4f} | {r['recall']:.4f} | {r['f1']:.4f} | {r['alerts']:,} | {r['fp']:,} | {r['fn']:,} |")
    lines += ["", "## Faisabilité et limites", "",
              "Les temps ont été mesurés sur macOS Apple Silicon avec Python 3.11 et au plus quatre fils par modèle. "
              "La mémoire ci-dessous est le pic RSS échantillonné chaque seconde par l'orchestrateur : "
              "elle peut manquer un pic bref. La limite était 12 Gio par processus et 30 minutes pour "
              "l'exécution complète d'une fenêtre. Le temps d'ajustement du tableau exclut la lecture du CSV "
              "et la construction des variables ; le temps de choix du seuil comprend la prédiction sur la réserve "
              "et la recherche du F1 maximal ; le temps de prédiction extérieure exclut sa construction de variables. "
              "Le temps total comprend la lecture, les transformations et la sérialisation en mémoire. "
              "Les étapes ont été lancées séquentiellement. Les données et les journaux détaillés restent locaux.", "",
              "| Modèle | Fenêtres achevées | Temps total d'ajustement | Pic RSS observé | Taille sérialisée, fenêtre 5 | État |",
              "| --- | ---: | ---: | ---: | ---: | --- |"]
    for name in MODELS:
        values = by_model[name]
        relevant = [status.get(f"{name}_fold_{fold}", {}) for fold in range(1, 6)]
        failed = next((s for s in relevant if s.get("state") == "failed"), None)
        state = f"échec : {failed.get('reason') or 'voir journal local'}" if failed else ("complet" if len(values) == 5 else "non exécuté ou partiel")
        if name == "svc_rbf" and svc_trial and not values:
            state = "essai complet interrompu au contrôle de coût"
        peak = max((s.get("peak_rss_bytes", 0) for s in relevant), default=0)
        size = next((r["serialized_bytes"] for r in values if r["fold"] == 5), None)
        lines.append(f"| {name} | {len(values)}/5 | {sum(r['fit_seconds'] for r in values):.1f} s | {peak/2**30:.2f} Gio | {size/2**20:.2f} Mio | {state} |" if size is not None else f"| {name} | {len(values)}/5 | {sum(r['fit_seconds'] for r in values):.1f} s | {peak/2**30:.2f} Gio | absent | {state} |")
    if svc_trial:
        lines += ["", "Le SVM à noyau a été essayé sur la première fenêtre complète. "
                  f"Après au moins **{svc_trial['minimum_elapsed_seconds_observed']} s** sans résultat, "
                  "l'essai a été interrompu pour préserver le budget du prototype. "
                  "Ce constat ne prouve pas qu'il dépasserait 30 minutes ni qu'il serait moins précis. "
                  "Aucun F1 sur sous-ensemble ne lui est attribué."]
    if feasibility:
        lines += ["", "Les essais API sur 10 000 et 20 000 lignes, ainsi que la mesure KNN "
                  "sur la première portion d'apprentissage complète, sont conservés dans "
                  "[le fichier structuré](results/ml_benchmark.json). Les petits échantillons "
                  "ne sont pas des validations comparables."]
    lines += ["", "Ces mesures comparent des **pipelines** : `type` est représenté par cinq indicatrices fixes, "
              "sauf CatBoost qui reçoit sa catégorie native ; les modèles linéaires, GaussianNB et MLP utilisent "
              "`log1p(amount)` standardisé sur l'apprentissage de la fenêtre, comme KNN ; les arbres reçoivent le montant brut. "
              "Le premier passage n'utilise aucune pondération ni rééchantillonnage. Le code, les versions et chaque "
              "résultat numérique se trouvent dans [le fichier structuré](results/ml_benchmark.json). "
              "Aucun score n'est qualifié de probabilité calibrée. Les cinq fenêtres partagent des entraînements "
              "et ne sont pas cinq expériences indépendantes. La dernière validation est plus courte et plus riche "
              "en fraudes ; les moyennes seules ne décrivent pas cette variation. L'EDA avait déjà exposé les labels "
              "du futur test, même si aucun score de test n'a servi ici.", ""]
    if winner:
        top = next(item for item in summary if item["model"] == winner)
        lines += ["## Lecture provisoire", "",
                  f"`{winner}` obtient un F1 moyen de **{top['f1_mean']:.4f}**, "
                  f"avec une précision moyenne de **{top['precision_mean']:.4f}** et "
                  f"un rappel moyen de **{top['recall_mean']:.4f}**. "
                  f"Ses cinq validations totalisent **{top['fp_total']:,} faux positifs** "
                  f"et **{top['fn_total']:,} fraudes manquées**. Ces effectifs sont additionnés "
                  "sur les validations, tandis que les métriques affichées sont des moyennes "
                  "par fenêtre, pas les ratios calculés sur les effectifs additionnés.", "",
                  "Les fortes variations de certains candidats entre fenêtres sont observées, "
                  "mais leurs causes ne sont pas encore démontrées. La prévalence, la taille "
                  "des validations, les seuils internes et les représentations diffèrent ; "
                  "les diagnostics par type et montant ainsi que des comparaisons contrôlées "
                  "restent à discuter avant la phase 2. Aucun candidat n'a été évalué sur "
                  "le test 505 à 743.", ""]
    args.report.write_text("\n".join(lines).rstrip() + "\n")
    print(f"{len(rows)} résultats, {len(summary)} modèles complets : {args.report}")


if __name__ == "__main__":
    main()
