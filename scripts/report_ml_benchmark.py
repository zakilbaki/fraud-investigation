"""Publier les résultats agrégés des cinq fenêtres, sans données individuelles."""

import argparse
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fraud_investigation.ml_benchmark import MODELS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/ml_benchmark"))
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
    payload = {"rows": rows, "summary": summary, "status": status}
    result_path = Path("docs/results/ml_benchmark.json")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    figures = Path("docs/figures")
    figures.mkdir(exist_ok=True)
    if summary:
        labels = [r["model"].replace("_", " ") for r in summary]
        positions = np.arange(len(labels))
        fig, ax = plt.subplots(figsize=(13, max(5, len(labels) * 0.45)))
        height = 0.25
        for offset, key, title in [(-height, "precision_mean", "Précision"), (0, "recall_mean", "Rappel"), (height, "f1_mean", "F1")]:
            ax.barh(positions + offset, [r[key] for r in summary], height, label=title)
        ax.set_yticks(positions, labels)
        ax.invert_yaxis()
        ax.set_xlim(0, 1)
        ax.set_xlabel("Moyenne arithmétique des cinq validations")
        ax.set_title("Comparaison des modèles, seuil choisi dans chaque train")
        ax.legend()
        fig.tight_layout()
        fig.savefig(figures / "ml_model_means.png", dpi=160)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(13, 6))
        for name in complete:
            values = complete[name]
            ax.plot([r["fold"] for r in values], [r["f1"] for r in values], marker="o", label=name.replace("_", " "))
        ax.set_xticks(range(1, 6), [f"{f}\n{complete[next(iter(complete))][f-1]['prevalence']*100:.3f} %" for f in range(1, 6)])
        ax.set_xlabel("Fenêtre extérieure et taux de fraude")
        ax.set_ylabel("F1 sur validation extérieure")
        ax.set_title("Évolution du F1 entre périodes, seuil interne figé")
        ax.grid(alpha=0.2)
        ax.legend(ncol=3, fontsize=8)
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
    lines += ["", "![Moyennes des métriques](figures/ml_model_means.png)", "",
              "![F1 par fenêtre](figures/ml_model_windows.png)", "",
              "## Détail par modèle et fenêtre", "",
              "`P` = précision, `R` = rappel. `FP` = normales alertées ; `FN` = fraudes manquées. "
              "La précision est reportée à 0 par convention si aucune alerte n'est émise.", "",
              "| Modèle | Fenêtre | Transactions | Fraudes | Prévalence | Seuil interne | P | R | F1 | Alertes | FP | FN | Ajustement | Prédiction |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name in MODELS:
        for r in sorted(by_model[name], key=lambda x: x["fold"]):
            lines.append(f"| {name} | {r['fold']} | {r['transactions']:,} | {r['frauds']:,} | {r['prevalence']*100:.3f} % | {r['threshold']:.6g} | {r['precision']:.4f} | {r['recall']:.4f} | {r['f1']:.4f} | {r['alerts']:,} | {r['fp']:,} | {r['fn']:,} | {r['fit_seconds']:.1f} s | {r['predict_seconds']:.1f} s |")
    lines += ["", "## Faisabilité et limites", "",
              "Les temps ont été mesurés sur macOS Apple Silicon avec Python 3.11 et au plus quatre fils par modèle. "
              "La mémoire ci-dessous est le pic RSS échantillonné chaque seconde par l'orchestrateur : "
              "elle peut manquer un pic bref. La limite était 12 Gio par processus et 30 minutes par ajustement complet. "
              "Les étapes ont été lancées séquentiellement. Les fichiers de scores individuels et les données restent locaux.", "",
              "| Modèle | Fenêtres achevées | Temps total d'ajustement | Pic RSS observé | Taille sérialisée, fenêtre 5 | État |",
              "| --- | ---: | ---: | ---: | ---: | --- |"]
    for name in MODELS:
        values = by_model[name]
        relevant = [status.get(f"{name}_fold_{fold}", {}) for fold in range(1, 6)]
        failed = next((s for s in relevant if s.get("state") == "failed"), None)
        state = f"échec : {failed.get('reason') or 'voir journal local'}" if failed else ("complet" if len(values) == 5 else "non exécuté ou partiel")
        peak = max((s.get("peak_rss_bytes", 0) for s in relevant), default=0)
        size = next((r["serialized_bytes"] for r in values if r["fold"] == 5), None)
        lines.append(f"| {name} | {len(values)}/5 | {sum(r['fit_seconds'] for r in values):.1f} s | {peak/2**30:.2f} Gio | {size/2**20:.2f} Mio | {state} |" if size is not None else f"| {name} | {len(values)}/5 | {sum(r['fit_seconds'] for r in values):.1f} s | {peak/2**30:.2f} Gio | absent | {state} |")
    lines += ["", "Ces mesures comparent des **pipelines** : `type` est représenté par cinq indicatrices fixes, "
              "sauf CatBoost qui reçoit sa catégorie native ; les modèles linéaires, GaussianNB et MLP utilisent "
              "`log1p(amount)` standardisé sur l'apprentissage de la fenêtre, les arbres reçoivent le montant brut. "
              "Le premier passage n'utilise aucune pondération ni rééchantillonnage. Le code, les versions et chaque "
              "résultat numérique se trouvent dans [le fichier structuré](results/ml_benchmark.json). "
              "Aucun score n'est qualifié de probabilité calibrée. Les cinq fenêtres partagent des entraînements "
              "et ne sont pas cinq expériences indépendantes. La dernière validation est plus courte et plus riche "
              "en fraudes ; les moyennes seules ne décrivent pas cette variation. L'EDA avait déjà exposé les labels "
              "du futur test, même si aucun score de test n'a servi ici.", ""]
    args.report.write_text("\n".join(lines) + "\n")
    print(f"{len(rows)} résultats, {len(summary)} modèles complets : {args.report}")


if __name__ == "__main__":
    main()
