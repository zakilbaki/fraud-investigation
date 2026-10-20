"""Vérifier et publier les quinze validations XGBoost de réglage de H."""

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

from fraud_investigation.ml_benchmark import EXPECTED_COUNTS, FOLDS
from fraud_investigation.ml_feature_ratio_recipient_history import RatioRecipientFeatures, SOURCE_COLUMNS
from fraud_investigation.ml_tune_h import CONFIGS, EXPERIMENT, configured_model

SHA256 = "16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b"
CODES = ("H", "xgb_depth4", "xgb_lambda10", "xgb_slow200")
METRICS = ("precision", "recall", "f1")


def fmt(x, n=4):
    return "n.d." if x is None else f"{x:.{n}f}"


def table(headers, records):
    return ["| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] + ["---:"] * (len(headers)-1)) + " |",
            *["| " + " | ".join(str(v) for v in record) + " |" for record in records]]


def verified_metric(row):
    assert row["tp"] + row["fn"] == row["frauds"]
    assert row["tn"] + row["fp"] == row["transactions"] - row["frauds"]
    assert row["alerts"] == row["tp"] + row["fp"]
    assert row["precision"] == (row["tp"] / row["alerts"] if row["alerts"] else None)
    assert row["recall"] == row["tp"] / row["frauds"]
    assert abs(row["f1"] - 2*row["tp"]/(2*row["tp"]+row["fp"]+row["fn"])) < 1e-12
    assert row["prevalence"] == row["frauds"] / row["transactions"]


def main():
    csv_path = Path("data/raw/PS_20174392719_1491204439457_log.csv")
    with csv_path.open("rb") as file:
        assert hashlib.file_digest(file, "sha256").hexdigest() == SHA256
    h = json.loads(Path("docs/results/ml_feature_ratio_recipient_history.json").read_text())
    assert h["source_sha256"] == SHA256
    base = {r["fold"]: r for r in h["rows"] if r["model"] == "xgboost"}
    assert len(base) == 5
    source = Path("data/ml_tune_h")
    status = json.loads((source / "status.json").read_text())
    rows = []
    for code in CODES[1:]:
        model = configured_model(code)
        expected_params = {k: ("NaN" if isinstance(v, float) and np.isnan(v) else v)
                           for k, v in model.get_params().items()}
        for fold in range(1, 6):
            key = f"{code}_fold_{fold}"
            assert status[key]["state"] == "ok" and status[key]["reason"] is None
            row = json.loads((source / f"{key}.json").read_text())
            ref = base[fold]
            assert row["experiment"] == EXPERIMENT and row["config"] == code
            assert row["model"] == "xgboost" and row["fold"] == fold
            assert row["parameter_changes"] == CONFIGS[code][1]
            assert row["model_parameters"] == expected_params
            assert row["versions"] == ref["versions"] and row["random_seed"] == 42
            assert row["source_columns"] == ref["source_columns"] == list(SOURCE_COLUMNS)
            assert row["history_source_columns"] == ref["history_source_columns"] == ["step", "nameDest"]
            assert row["predictor_columns"] == ref["predictor_columns"] == RatioRecipientFeatures("xgboost").columns
            assert row["raw_step_predictor"] is False and row["raw_account_predictor"] is False
            a, b, c = FOLDS[fold-1]
            assert row["fit_steps"] == ref["fit_steps"] == [1, a]
            assert row["threshold_steps"] == ref["threshold_steps"] == [a+1, b]
            assert row["validation_steps"] == ref["validation_steps"] == [b+1, c]
            assert (row["fit_rows"], row["fit_frauds"]) == EXPECTED_COUNTS[fold-1][0]
            assert (row["threshold_rows"], row["threshold_frauds"]) == EXPECTED_COUNTS[fold-1][1]
            assert (row["transactions"], row["frauds"]) == EXPECTED_COUNTS[fold-1][2]
            for key2 in ("ratio_undefined_rows", "ratio_above_one_rows", "history_nonzero_rows"):
                assert row[key2] == ref[key2]
            assert np.isfinite(row["threshold"]) and 0 <= row["threshold"] <= 1
            verified_metric(row)
            verified_metric(row["fit_metrics"])
            assert row["fit_metrics"]["transactions"] == row["fit_rows"]
            assert row["fit_metrics"]["frauds"] == row["fit_frauds"]
            assert row["serialized_bytes"] > 0 and status[key]["peak_rss_bytes"] > 0
            assert all(row[k] >= 0 for k in ("read_seconds", "history_seconds", "fit_build_seconds",
                "threshold_build_seconds", "validation_build_seconds", "fit_seconds", "threshold_seconds",
                "fit_predict_seconds", "predict_seconds", "total_seconds"))
            row["peak_rss_bytes"] = status[key]["peak_rss_bytes"]
            rows.append(row)
    by_code = {"H": [base[i] for i in range(1, 6)]}
    by_code.update({code: [r for r in rows if r["config"] == code] for code in CODES[1:]})
    summary = []
    for code, records in by_code.items():
        assert len(records) == 5 and all(r[k] is not None for r in records for k in METRICS)
        item = {"config": code, **{f"{m}_mean": statistics.mean(r[m] for r in records) for m in METRICS},
                "f1_min": min(r["f1"] for r in records),
                "f1_std": statistics.stdev(r["f1"] for r in records),
                **{f"{k}_total": sum(r[k] for r in records) for k in ("tp", "fp", "fn", "tn", "alerts")},
                "fit_seconds_median": statistics.median(r["fit_seconds"] for r in records),
                "serialized_bytes_median": statistics.median(r["serialized_bytes"] for r in records)}
        if code != "H":
            item["peak_rss_bytes"] = max(r["peak_rss_bytes"] for r in records)
            item["total_seconds_total"] = sum(r["total_seconds"] for r in records)
        summary.append(item)
    # La sélection complète attend les variantes CatBoost. Ici, seulement un classement descriptif XGBoost.
    output = {"experiment": EXPERIMENT, "status": "xgboost_only_waiting_for_user",
              "source_sha256": SHA256, "configs": {k: {"model": v[0], "changes": v[1]} for k, v in CONFIGS.items()},
              "reference_rows": by_code["H"], "rows": rows, "summary": summary,
              "selection_pending": "CatBoost non exécuté ; aucune sélection entre familles"}
    result_path = Path("docs/results/ml_tune_h_xgboost.json")
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    figure_dir = Path("docs/figures")
    plt.rcParams.update({"font.size": 10})
    fig, axes = plt.subplots(1, 3, figsize=(16, 4), sharey=True)
    x = np.arange(len(CODES))
    for axis, metric in zip(axes, METRICS):
        axis.bar(x, [next(s[f"{metric}_mean"] for s in summary if s["config"] == c) for c in CODES])
        axis.set_xticks(x, CODES, rotation=20, ha="right")
        axis.set_title(metric.capitalize())
        axis.set_ylim(0, 1)
    axes[0].set_ylabel("Moyenne des cinq validations")
    fig.tight_layout(); fig.savefig(figure_dir / "ml_tune_h_xgboost_means.png", dpi=140); plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4))
    for code in CODES:
        ax.plot(range(1, 6), [r["f1"] for r in by_code[code]], marker="o", label=code)
    ax.set(xlabel="Fenêtre chronologique", ylabel="F1 sur validation extérieure", ylim=(0, 1))
    ax.set_xticks(range(1, 6)); ax.legend(); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(figure_dir / "ml_tune_h_xgboost_windows.png", dpi=140); plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for axis, key, title in zip(axes, ("tp_total", "fp_total", "fit_seconds_median"),
                                 ("Fraudes détectées", "Fausses alertes", "Ajustement médian, s")):
        axis.bar(CODES, [next(s[key] for s in summary if s["config"] == c) for c in CODES])
        axis.set_title(title); axis.tick_params(axis="x", rotation=20)
    fig.tight_layout(); fig.savefig(figure_dir / "ml_tune_h_xgboost_counts_cost.png", dpi=140); plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4))
    for code in CODES[1:]:
        ax.plot(range(1, 6), [r["fit_metrics"]["f1"]-r["f1"] for r in by_code[code]],
                marker="o", label=code)
    ax.axhline(0, color="black", linewidth=.8)
    ax.set(xlabel="Fenêtre chronologique", ylabel="F1 apprentissage moins validation")
    ax.set_xticks(range(1, 6)); ax.legend(); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(figure_dir / "ml_tune_h_xgboost_train_gap.png", dpi=140); plt.close(fig)
    lines = ["# Lot 4.4 : réglages XGBoost avec les variables de H", "",
             "Les configurations des deux familles ont été figées dans [le protocole](ML_PROTOCOL.md) avant les nouveaux scores. Seules les quinze exécutions XGBoost ont commencé. CatBoost attend la discussion. H est réutilisée sans réentraînement. Les métriques d'apprentissage de H n'avaient pas été enregistrées ; son écart apprentissage/validation est donc non disponible.", "",
             "## Moyennes des cinq validations", "",
             "Les moyennes sont arithmétiques et distinctes des effectifs cumulés. Les cinq fenêtres se recouvrent par l'apprentissage et ne forment pas cinq expériences indépendantes.", ""]
    lines += table(["Configuration", "Précision", "Rappel", "F1", "F1 min", "Écart-type F1"],
                   [[s["config"], *[fmt(s[f"{m}_mean"]) for m in METRICS], fmt(s["f1_min"]), fmt(s["f1_std"])] for s in summary])
    lines += ["", "![Moyennes](figures/ml_tune_h_xgboost_means.png)", "", "![F1 par fenêtre](figures/ml_tune_h_xgboost_windows.png)", "",
              "## Fenêtres, seuils et apprentissage", "",
              "Chaque seuil maximise F1 sur la réserve interne seulement. Les prévalences sont `fraudes / transactions`. Les métriques d'apprentissage emploient ce même seuil, choisi après l'ajustement.", ""]
    lines += table(["Config", "Fen.", "Seuil", "P val", "R val", "F1 val", "P app.", "R app.", "F1 app.", "Prév. app. %", "Prév. val %"],
                   [[r["config"], r["fold"], fmt(r["threshold"], 6), *[fmt(r[k]) for k in METRICS],
                     *[fmt(r["fit_metrics"][k]) for k in METRICS], fmt(100*r["fit_metrics"]["prevalence"], 3),
                     fmt(100*r["prevalence"], 3)] for r in rows])
    lines += ["", "### Écarts à H sur les mêmes fenêtres", "",
              "Un écart positif de F1 ou de TP et un écart négatif de FP n'ont pas la même signification. Les seuils diffèrent entre H et chaque variante.", ""]
    lines += table(["Config", "Fen.", "ΔP", "ΔR", "ΔF1", "ΔTP", "ΔFP", "F1 H"],
                   [[r["config"], r["fold"], *[fmt(r[m]-base[r["fold"]][m]) for m in METRICS],
                     r["tp"]-base[r["fold"]]["tp"], r["fp"]-base[r["fold"]]["fp"],
                     fmt(base[r["fold"]]["f1"])] for r in rows])
    lines += ["", "![Écart F1 apprentissage et validation](figures/ml_tune_h_xgboost_train_gap.png)", "",
              "Un écart peut aussi provenir du changement de prévalence et de période ; il ne prouve pas seul un surapprentissage.", "",
              "## Alertes et coûts", ""]
    lines += table(["Config", "Fen.", "Alertes", "TP", "FP", "FN", "TN", "Fit s", "Préd. val s", "Total s", "Pic Gio", "Taille Mio"],
                   [[r["config"], r["fold"], *[r[k] for k in ("alerts", "tp", "fp", "fn", "tn")],
                     fmt(r["fit_seconds"], 2), fmt(r["predict_seconds"], 2), fmt(r["total_seconds"], 2),
                     fmt(r["peak_rss_bytes"]/2**30, 2), fmt(r["serialized_bytes"]/2**20, 2)] for r in rows])
    lines += ["", "Les cumuls de la référence H et des variantes sont :", ""]
    lines += table(["Config", "TP", "FP", "FN", "Alertes", "Fit médian s", "Taille médiane Mio"],
                   [[s["config"], *[s[f"{k}_total"] for k in ("tp", "fp", "fn", "alerts")],
                     fmt(s["fit_seconds_median"], 2), fmt(s["serialized_bytes_median"]/2**20, 2)] for s in summary])
    lines += ["", "![Fraudes, fausses alertes et temps](figures/ml_tune_h_xgboost_counts_cost.png)", "",
              "## Lecture provisoire", "",
              "Parmi les quatre configurations XGBoost, `xgb_depth4` a le F1 moyen le plus élevé (0,9000 contre 0,8948 pour H), le meilleur minimum (0,8731 contre 0,8622), 30 TP de plus et 9 FP de moins. Le F1 baisse toutefois légèrement face à H dans les fenêtres 3 et 4. `xgb_lambda10` varie peu en moyenne et baisse dans trois fenêtres. `xgb_slow200` se rapproche de `depth4`, mais son ajustement médian est plus long et son modèle médian plus gros. Avec la règle préannoncée et les seules configurations XGBoost, `xgb_depth4` est le candidat provisoire : plusieurs moyennes sont à moins de 0,005 du meilleur, puis son F1 minimum est le plus haut. La sélection globale attend les variantes CatBoost et la discussion avec l'utilisateur.", "",
              "## Limites et suite", "",
              "La règle de sélection complète attend CatBoost. Les seuils sont réestimés par configuration. Les mesures de coût proviennent d'exécutions séparées et ne constituent pas un benchmark contrôlé de vitesse. Le pic RSS est échantillonné et peut manquer un pic bref. Ratio montant/solde et heure peuvent refléter des signatures du simulateur. Les validations ont déjà guidé plusieurs choix ; les labels du test ont été examinés en EDA, sans score du test 505 à 743 ici. Aucune généralisation réelle ni modèle final ne sont annoncés.", "",
              "Réexécution locale : `python scripts/run_ml_tune_h_xgboost_all.py`, puis `python scripts/report_ml_tune_h_xgboost.py`, avec les prérequis du README. Aucun fichier de transaction ni prédiction individuelle n'est publié.", ""]
    Path("docs/ML_TUNE_H_XGBOOST.md").write_text("\n".join(lines))
    print("Réglage H XGBoost : 15 validations vérifiées, rapport et figures produits")


if __name__ == "__main__":
    main()
