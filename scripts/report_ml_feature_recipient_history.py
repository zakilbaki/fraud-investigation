"""Vérifier les résultats G et publier leur comparaison avec D."""

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
from fraud_investigation.ml_feature_recipient_history import (
    EXPERIMENT, MODELS, RecipientFeatures, SOURCE_COLUMNS,
)

EXPECTED_SHA256 = "16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b"


def show(value, digits=4):
    return "n.d." if value is None else f"{value:.{digits}f}"


def table(headers, records):
    return ["| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] + ["---:"] * (len(headers)-1)) + " |",
            *["| " + " | ".join(str(x) for x in record) + " |" for record in records]]


def main():
    csv_path = Path("data/raw/PS_20174392719_1491204439457_log.csv")
    with csv_path.open("rb") as csv_file:
        source_sha256 = hashlib.file_digest(csv_file, "sha256").hexdigest()
    assert source_sha256 == EXPECTED_SHA256
    local = Path("data/ml_feature_recipient_history")
    prior_result = json.loads(Path("docs/results/ml_feature_balance_org_hour.json").read_text())
    coverage = json.loads(Path("docs/results/ml_recipient_history_coverage.json").read_text())
    assert coverage["source_sha256"] == source_sha256 and coverage["max_step"] == 504
    reference = {(r["model"], r["fold"]): r for r in prior_result["rows"]}
    status = json.loads((local / "status.json").read_text())
    rows = []
    deltas = []
    for model in MODELS:
        for fold in range(1, 6):
            key = f"{model}_fold_{fold}"
            assert status[key]["state"] == "ok"
            r = json.loads((local / f"{key}.json").read_text())
            d = reference[model, fold]
            counts = EXPECTED_COUNTS[fold-1]
            assert r["experiment"] == EXPERIMENT and r["model"] == model and r["fold"] == fold
            assert r["source_columns"] == list(SOURCE_COLUMNS)
            assert r["history_source_columns"] == ["step", "nameDest"]
            assert r["predictor_columns"] == RecipientFeatures(model).columns
            assert r["predictor_columns"] == [*d["predictor_columns"], "nb_entrees_anterieures"]
            assert r["raw_step_predictor"] is False and r["raw_account_predictor"] is False
            assert not set(r["predictor_columns"]) & {
                "step", "nameDest", "nameOrig", "isFraud", "isFlaggedFraud", "part_solde",
                "oldbalanceDest", "newbalanceOrig", "newbalanceDest", "nb_sorties_anterieures"}
            assert r["fit_steps"] == d["fit_steps"] == [1, FOLDS[fold-1][0]]
            assert r["threshold_steps"] == d["threshold_steps"] == [FOLDS[fold-1][0]+1, FOLDS[fold-1][1]]
            assert r["validation_steps"] == d["validation_steps"] == [FOLDS[fold-1][1]+1, FOLDS[fold-1][2]]
            assert (r["fit_rows"], r["fit_frauds"]) == counts[0]
            assert (r["threshold_rows"], r["threshold_frauds"]) == counts[1]
            assert (r["transactions"], r["frauds"]) == counts[2]
            assert r["versions"] == d["versions"] and r["random_seed"] == d["random_seed"] == 42
            assert r["model_parameters"] == d["model_parameters"]
            assert r["model_parameters"] == {
                k: ("NaN" if isinstance(v, float) and np.isnan(v) else v)
                for k, v in candidate(model).get_params().items()}
            for part in ("fit", "threshold", "validation"):
                assert r["history_nonzero_rows"][part] == coverage["windows"][fold-1][part]["nonzero_transactions"]
            assert np.isfinite(r["threshold"]) and 0 <= r["threshold"] <= 1
            assert all(r[field] >= 0 for field in (
                "read_seconds", "history_seconds", "fit_seconds", "threshold_seconds",
                "predict_seconds", "total_seconds"))
            assert r["history_rss_after_bytes"] > 0 and status[key]["peak_rss_bytes"] > 0
            assert r["tp"] + r["fn"] == r["frauds"]
            assert r["tn"] + r["fp"] == r["transactions"] - r["frauds"]
            assert r["alerts"] == r["tp"] + r["fp"]
            assert r["precision"] == (r["tp"] / r["alerts"] if r["alerts"] else None)
            assert r["recall"] == r["tp"] / r["frauds"]
            assert abs(r["f1"] - 2*r["tp"]/(2*r["tp"]+r["fp"]+r["fn"])) < 1e-12
            rows.append(r)
            deltas.append({"model": model, "fold": fold, **{
                f"delta_{metric}": (r[metric]-d[metric]
                                    if r[metric] is not None and d[metric] is not None else None)
                for metric in ("precision", "recall", "f1", "tp", "fp", "fn", "alerts")}})
    assert len(rows) == 10
    summary = []
    for model in MODELS:
        g = [r for r in rows if r["model"] == model]
        d = [reference[model, fold] for fold in range(1, 6)]
        item = {"model": model}
        for metric in ("precision", "recall", "f1"):
            item[f"g_{metric}_mean"] = statistics.mean(r[metric] for r in g) if all(r[metric] is not None for r in g) else None
            item[f"d_{metric}_mean"] = statistics.mean(r[metric] for r in d) if all(r[metric] is not None for r in d) else None
            item[f"delta_{metric}_mean"] = (item[f"g_{metric}_mean"]-item[f"d_{metric}_mean"]
                                           if item[f"g_{metric}_mean"] is not None and item[f"d_{metric}_mean"] is not None else None)
        for tag, group in (("g", g), ("d", d)):
            item[f"{tag}_f1_min"] = min(r["f1"] for r in group)
            item[f"{tag}_f1_std"] = statistics.stdev(r["f1"] for r in group)
            for field in ("tp", "fp", "fn", "tn", "alerts", "fit_seconds", "threshold_seconds",
                          "predict_seconds", "total_seconds"):
                item[f"{tag}_{field}_total"] = sum(r[field] for r in group)
        item["g_history_seconds_total"] = sum(r["history_seconds"] for r in g)
        item["g_history_rss_after_bytes_max"] = max(r["history_rss_after_bytes"] for r in g)
        item["g_peak_rss_bytes"] = max(status[f"{model}_fold_{i}"]["peak_rss_bytes"] for i in range(1, 6))
        item["d_peak_rss_bytes"] = max(prior_result["status"][f"{model}_fold_{i}"]["peak_rss_bytes"] for i in range(1, 6))
        summary.append(item)
    Path("docs/results/ml_feature_recipient_history.json").write_text(json.dumps({
        "experiment": EXPERIMENT, "source_sha256": source_sha256,
        "comparison_source": "ml_feature_balance_org_hour.json",
        "coverage_source": "ml_recipient_history_coverage.json",
        "rows": rows, "summary": summary, "deltas": deltas, "status": status,
    }, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

    figdir = Path("docs/figures")
    labels = ["XGBoost", "CatBoost"]
    x = np.arange(2)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
    for ax, metric, title in zip(axes, ("precision", "recall", "f1"), ("Précision", "Rappel", "F1")):
        ax.bar(x-.18, [s[f"d_{metric}_mean"] for s in summary], .36, label="D", color="#587d9a")
        ax.bar(x+.18, [s[f"g_{metric}_mean"] for s in summary], .36, label="G", color="#df9459")
        ax.set_xticks(x, labels)
        ax.set_ylim(0, 1)
        ax.set_title(title)
        ax.grid(axis="y", alpha=.2)
    axes[0].set_ylabel("Moyenne sur cinq validations")
    axes[-1].legend()
    fig.tight_layout()
    fig.savefig(figdir / "ml_feature_recipient_history_means.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, model, title in zip(axes, MODELS, labels):
        ax.plot(range(1, 6), [reference[model, i]["f1"] for i in range(1, 6)],
                marker="o", label="D", color="#587d9a")
        ax.plot(range(1, 6), [r["f1"] for r in rows if r["model"] == model],
                marker="s", label="G", color="#df9459")
        ax.set_title(title)
        ax.set_xticks(range(1, 6))
        ax.set_ylim(0, 1)
        ax.grid(alpha=.2)
    axes[0].set_ylabel("F1 sur validation extérieure")
    axes[1].legend()
    fig.supxlabel("Fenêtre chronologique")
    fig.tight_layout()
    fig.savefig(figdir / "ml_feature_recipient_history_windows.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, field, title in zip(axes, ("tp", "fp"), ("Fraudes détectées, TP", "Fausses alertes, FP")):
        ax.barh(x-.18, [s[f"d_{field}_total"] for s in summary], .36, label="D", color="#587d9a")
        ax.barh(x+.18, [s[f"g_{field}_total"] for s in summary], .36, label="G", color="#df9459")
        ax.set_yticks(x, labels)
        ax.invert_yaxis()
        ax.set_title(title)
        ax.set_xlabel("Effectif cumulé sur cinq validations")
        ax.grid(axis="x", alpha=.2)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(figdir / "ml_feature_recipient_history_counts.png", dpi=160)
    plt.close(fig)

    lines = ["# Lot 4.4, expérience G : activité passée du destinataire", "",
             "G ajoute seulement `nb_entrees_anterieures` aux entrées de [D](ML_FEATURE_BALANCE_ORG_HOUR.md) : "
             "`type`, `amount`, `oldbalanceOrg`, `hour_sin`, `hour_cos`. Le compteur est le nombre "
             "de transactions du même `nameDest` aux steps strictement inférieurs. Il reste brut en "
             "`float32`, sans transformation apprise. `nameDest` sert uniquement au calcul ; le ratio "
             "de E et le compteur émetteur F n'entrent pas dans G. D est réutilisée sans réentraînement.", "",
             "Chaque modèle apprend sur la première portion, choisit son seuil par F1 maximal dans la "
             "réserve interne avec scores identiques groupés et seuil le plus haut à égalité, puis est "
             "mesuré sur la validation extérieure. Une précision sans alerte reste non définie. Les "
             "steps 505 à 743 ne sont pas lus pour les prédictions.", "",
             "## Moyennes et effectifs cumulés", "",
             "Chaque moyenne est arithmétique sur cinq fenêtres. Les effectifs TP, FP, FN et alertes sont "
             "additionnés sur cinq validations disjointes. `Δ` signifie G moins D.", ""]
    lines += table(["Modèle", "P D", "P G", "ΔP", "R D", "R G", "ΔR", "F1 D", "F1 G", "ΔF1",
                    "TP D → G", "FP D → G", "FN D → G", "Alertes D → G"], [
        [s["model"], show(s["d_precision_mean"]), show(s["g_precision_mean"]), show(s["delta_precision_mean"]),
         show(s["d_recall_mean"]), show(s["g_recall_mean"]), show(s["delta_recall_mean"]),
         show(s["d_f1_mean"]), show(s["g_f1_mean"]), show(s["delta_f1_mean"]),
         f"{s['d_tp_total']:,} → {s['g_tp_total']:,}", f"{s['d_fp_total']:,} → {s['g_fp_total']:,}",
         f"{s['d_fn_total']:,} → {s['g_fn_total']:,}", f"{s['d_alerts_total']:,} → {s['g_alerts_total']:,}"]
        for s in summary])
    lines += ["", "![Moyennes D et G](figures/ml_feature_recipient_history_means.png)", "",
              "Axes : modèles en horizontal, moyenne de précision, rappel et F1 de 0 à 1 en vertical.", "",
              "![F1 de D et G par fenêtre](figures/ml_feature_recipient_history_windows.png)", "",
              "Axes : fenêtres 1 à 5 en horizontal, F1 de 0 à 1 en vertical, échelle commune.", "",
              "![TP et FP cumulés](figures/ml_feature_recipient_history_counts.png)", "",
              "Axes : effectifs cumulés linéaires, séparés entre fraudes détectées et fausses alertes.", "",
              "## Résultats par modèle et fenêtre", "",
              "Le seuil, les cases de confusion, les temps et la mémoire concernent G. `n.d.` signifie "
              "précision non définie. Les Δ comparent G à D sur la même validation.", ""]
    delta_map = {(d["model"], d["fold"]): d for d in deltas}
    detail_records = []
    for r in rows:
        delta = delta_map[r["model"], r["fold"]]
        peak = status[f"{r['model']}_fold_{r['fold']}"]["peak_rss_bytes"] / 2**30
        detail_records.append([
            r["model"], r["fold"], f"{r['transactions']:,}", f"{r['frauds']:,}",
            f"{r['threshold']:.6g}", show(r["precision"]), show(r["recall"]), show(r["f1"]),
            show(delta["delta_precision"]), show(delta["delta_recall"]), show(delta["delta_f1"]),
            f"{r['tp']:,}", f"{r['fp']:,}", f"{r['fn']:,}", f"{r['tn']:,}", f"{r['alerts']:,}",
            f"{delta['delta_tp']:+,}", f"{delta['delta_fp']:+,}",
            f"{r['history_seconds']:.1f} s", f"{r['history_rss_after_bytes']/2**30:.2f} Gio",
            f"{r['fit_seconds']:.1f} s", f"{r['threshold_seconds']:.1f} s",
            f"{r['predict_seconds']:.2f} s", f"{r['total_seconds']:.1f} s", f"{peak:.2f} Gio"])
    lines += table(["Modèle", "Fenêtre", "Transactions", "Fraudes", "Seuil G", "P G", "R G", "F1 G",
                    "ΔP", "ΔR", "ΔF1", "TP", "FP", "FN", "TN", "Alertes", "ΔTP", "ΔFP",
                    "Construction historique", "RSS après historique", "Ajustement", "Seuil",
                    "Prédiction", "Total", "Pic RSS"], detail_records)
    lines += ["", "## Régularité et coûts", "",
              "L'écart-type est descriptif : les apprentissages se recouvrent et les cinq résultats ne "
              "sont pas indépendants. L'historique complet 1 à 504 est reconstruit dans chacun des dix "
              "processus ; les temps de construction ci-dessous sont donc additionnés sur cinq exécutions "
              "par modèle. Le pic RSS est échantillonné, et le RSS après construction est un instantané.", ""]
    lines += table(["Modèle", "F1 min D → G", "Écart-type F1 D → G", "Ajustement D → G",
                    "Historique G", "Temps total D → G", "Pic RSS D → G"], [
        [s["model"], f"{s['d_f1_min']:.4f} → {s['g_f1_min']:.4f}",
         f"{s['d_f1_std']:.4f} → {s['g_f1_std']:.4f}",
         f"{s['d_fit_seconds_total']:.1f} → {s['g_fit_seconds_total']:.1f} s",
         f"{s['g_history_seconds_total']:.1f} s",
         f"{s['d_total_seconds_total']:.1f} → {s['g_total_seconds_total']:.1f} s",
         f"{s['d_peak_rss_bytes']/2**30:.2f} → {s['g_peak_rss_bytes']/2**30:.2f} Gio"]
        for s in summary])
    xgb = next(s for s in summary if s["model"] == "xgboost")
    cat = next(s for s in summary if s["model"] == "catboost")
    lines += ["", "## Observations et limites", "",
              f"Le F1 moyen augmente de {xgb['delta_f1_mean']:+.4f} pour XGBoost et de "
              f"{cat['delta_f1_mean']:+.4f} pour CatBoost face à D. Les dix comparaisons par "
              "fenêtre sont positives, mais le gain CatBoost de la première fenêtre est faible. "
              f"XGBoost détecte {xgb['g_tp_total']-xgb['d_tp_total']:,} fraudes supplémentaires "
              f"avec {xgb['g_fp_total']-xgb['d_fp_total']:,} fausses alertes supplémentaires ; "
              f"CatBoost en détecte {cat['g_tp_total']-cat['d_tp_total']:,} de plus avec "
              f"{cat['g_fp_total']-cat['d_fp_total']:,} fausses alertes de plus. La précision "
              "moyenne baisse pour les deux. Le F1 minimum s'améliore, tandis que l'écart-type "
              "des cinq F1 augmente : le niveau monte, mais sa variation temporelle aussi.", "",
              "La [couverture préalable](ML_RECIPIENT_HISTORY_COVERAGE.md) était de 56,5140 % sur les "
              "steps 1 à 504 ; elle ne garantissait aucun gain prédictif. Le résultat G mesure le "
              "pipeline enrichi avec son seuil réestimé : l'effet du nouveau compteur et celui du seuil "
              "ne sont pas séparés. Un destinataire fréquent n'est pas pour autant suspect ni animé "
              "d'une intention frauduleuse. Sa fréquence peut refléter le fonctionnement de PaySim, "
              "notamment des comptes commerçants. Les comptes bruts ne sont pas des prédicteurs. "
              "L'heure est simulée, les validations ont déjà guidé plusieurs analyses, les apprentissages "
              "se recouvrent et les labels du futur test avaient été examinés pendant l'EDA. Aucun "
              "modèle final n'est annoncé. Les résultats structurés conservent versions, paramètres, "
              "graines, colonnes et matrices agrégées ; les journaux et résultats intermédiaires restent "
              "hors de Git.", ""]
    Path("docs/ML_FEATURE_RECIPIENT_HISTORY.md").write_text("\n".join(lines))
    print("Expérience G : 10 validations vérifiées, rapport et figures produits")


if __name__ == "__main__":
    main()
