"""Comparer les huit configurations complètes selon la règle figée."""

import json
import math
import os
import statistics
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(".cache/matplotlib").resolve()))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fraud_investigation.ml_benchmark import EXPECTED_COUNTS

SOURCE = "16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b"
ORDER = ("xgb_H", "xgb_depth4", "xgb_lambda10", "xgb_slow200",
         "cat_H", "cat_depth4", "cat_l2leaf10", "cat_slow200")


def group(source, prefix):
    assert source["source_sha256"] == SOURCE and len(source["rows"]) == 15
    result = {f"{prefix}_H": source["reference_rows"]}
    for code in ORDER:
        if not code.startswith(prefix + "_") or code.endswith("_H"):
            continue
        result[code] = [r for r in source["rows"] if r["config"] == code]
    for code, rows in result.items():
        assert len(rows) == 5 and [r["fold"] for r in rows] == [1, 2, 3, 4, 5]
        for index, row in enumerate(rows):
            assert (row["transactions"], row["frauds"]) == EXPECTED_COUNTS[index][2]
            assert row["validation_steps"][1] <= 504
    return result


def summarize(code, rows):
    assert all(r["precision"] is not None for r in rows)
    return {"config": code,
            **{f"{k}_mean": statistics.mean(r[k] for r in rows) for k in ("precision", "recall", "f1")},
            "f1_min": min(r["f1"] for r in rows),
            "f1_std": statistics.stdev(r["f1"] for r in rows),
            **{f"{k}_total": sum(r[k] for r in rows) for k in ("tp", "fp", "fn", "alerts")},
            "fit_seconds_median": statistics.median(r["fit_seconds"] for r in rows),
            "serialized_bytes_median": statistics.median(r["serialized_bytes"] for r in rows)}


def select(summaries):
    """Appliquer les tolérances préannoncées sans arrondir les métriques."""
    steps = []
    best_mean = max(s["f1_mean"] for s in summaries)
    candidates = [s for s in summaries if best_mean - s["f1_mean"] < .005]
    steps.append({"criterion": "f1_mean_within_0.005", "candidates": [s["config"] for s in candidates]})
    best_min = max(s["f1_min"] for s in candidates)
    candidates = [s for s in candidates if best_min - s["f1_min"] < .005]
    steps.append({"criterion": "f1_min_within_0.005", "candidates": [s["config"] for s in candidates]})
    if len(candidates) > 1:
        best_std = min(s["f1_std"] for s in candidates)
        candidates = [s for s in candidates if s["f1_std"] - best_std < .005]
        steps.append({"criterion": "f1_std_within_0.005", "candidates": [s["config"] for s in candidates]})
    if len(candidates) > 1:
        fastest = min(s["fit_seconds_median"] for s in candidates)
        candidates = [s for s in candidates if s["fit_seconds_median"] < fastest * 1.2]
        steps.append({"criterion": "fit_time_within_20_percent", "candidates": [s["config"] for s in candidates]})
    if len(candidates) > 1:
        smallest = min(s["serialized_bytes_median"] for s in candidates)
        candidates = [s for s in candidates if s["serialized_bytes_median"] < smallest * 1.2]
        steps.append({"criterion": "size_within_20_percent", "candidates": [s["config"] for s in candidates]})
    if len(candidates) > 1:
        simple = {"xgb_depth4": 0, "xgb_H": 1, "xgb_lambda10": 2, "xgb_slow200": 3,
                  "cat_depth4": 4, "cat_H": 5, "cat_l2leaf10": 6, "cat_slow200": 7}
        candidates.sort(key=lambda s: (simple[s["config"]], s["config"]))
        steps.append({"criterion": "simplicity", "candidates": [s["config"] for s in candidates]})
    return candidates[0]["config"], steps


def main():
    x = json.loads(Path("docs/results/ml_tune_h_xgboost.json").read_text())
    c = json.loads(Path("docs/results/ml_tune_h_catboost.json").read_text())
    groups = group(x, "xgb") | group(c, "cat")
    assert set(groups) == set(ORDER)
    summaries = [summarize(code, groups[code]) for code in ORDER]
    for source, prefix in ((x, "xgb"), (c, "cat")):
        for item in source["summary"]:
            code = f"{prefix}_{item['config']}" if item["config"] == "H" else item["config"]
            actual = next(s for s in summaries if s["config"] == code)
            for field in ("precision_mean", "recall_mean", "f1_mean", "f1_min", "f1_std",
                          "tp_total", "fp_total", "fn_total", "alerts_total", "fit_seconds_median",
                          "serialized_bytes_median"):
                assert math.isclose(actual[field], item[field], abs_tol=1e-12)
    chosen, steps = select(summaries)
    result = {"source_sha256": SOURCE, "status": "selection_proposed_discussion_pending",
              "candidates": summaries, "selection": {"proposed": chosen, "steps": steps},
              "test_evaluated": False}
    Path("docs/results/ml_tune_h_selection.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    plt.rcParams.update({"font.size": 9})
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for ax, metric in zip(axes, ("precision", "recall", "f1")):
        ax.bar(range(len(ORDER)), [s[f"{metric}_mean"] for s in summaries])
        ax.set_xticks(range(len(ORDER)), ORDER, rotation=30, ha="right")
        ax.set_title(metric.capitalize()); ax.set_ylim(0, 1)
    axes[0].set_ylabel("Moyenne des cinq validations")
    fig.tight_layout(); fig.savefig("docs/figures/ml_tune_h_selection_means.png", dpi=140); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4))
    for code in ORDER:
        ax.plot(range(1, 6), [r["f1"] for r in groups[code]], marker="o", label=code)
    ax.set(xlabel="Fenêtre", ylabel="F1 validation", ylim=(0, 1))
    ax.set_xticks(range(1, 6)); ax.legend(ncol=4, fontsize=8); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig("docs/figures/ml_tune_h_selection_windows.png", dpi=140); plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, field, title in zip(axes, ("tp_total", "fp_total", "fit_seconds_median"),
                                ("Fraudes détectées, cumul", "Fausses alertes, cumul", "Ajustement médian, s")):
        ax.bar(range(len(ORDER)), [s[field] for s in summaries])
        ax.set_xticks(range(len(ORDER)), ORDER, rotation=30, ha="right")
        ax.set_title(title)
    fig.tight_layout(); fig.savefig("docs/figures/ml_tune_h_selection_counts_cost.png", dpi=140); plt.close(fig)
    header = "| Configuration | P moyen | R moyen | F1 moyen | F1 min | Écart-type F1 | TP | FP | Ajust. médian s | Taille médiane Mio |"
    lines = ["# Lot 4.4 : sélection proposée après réglages limités de H", "",
             "Les huit configurations comprennent H pour chaque famille et les six variantes figées avant les scores. Les 30 nouveaux ajustements ont terminé leurs cinq fenêtres. Les moyennes ci-dessous sont arithmétiques ; TP et FP sont des effectifs cumulés sur les validations disjointes. Les apprentissages se recouvrent.", "", header,
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in summaries:
        lines.append("| " + " | ".join([s["config"], *[f"{s[f'{m}_mean']:.4f}" for m in ("precision", "recall", "f1")],
            f"{s['f1_min']:.4f}", f"{s['f1_std']:.4f}", str(s["tp_total"]), str(s["fp_total"]),
            f"{s['fit_seconds_median']:.2f}", f"{s['serialized_bytes_median']/2**20:.3f}"]) + " |")
    lines += ["", "![Métriques moyennes](figures/ml_tune_h_selection_means.png)", "",
              "![F1 par fenêtre](figures/ml_tune_h_selection_windows.png)", "",
              "![Fraudes détectées, fausses alertes et coût](figures/ml_tune_h_selection_counts_cost.png)", "",
              "Les détails par fenêtre, seuil, apprentissage, mémoire et temps sont dans les [rapports XGBoost](ML_TUNE_H_XGBOOST.md) et [CatBoost](ML_TUNE_H_CATBOOST.md).", "",
              "## Application de la règle préannoncée", "",
              f"La configuration proposée est `{chosen}`. La sélection part du meilleur F1 moyen non arrondi, inclut les candidats à moins de 0,005, puis départage par F1 minimum et les critères suivants seulement si nécessaire. La trace exacte est dans les [résultats structurés](results/ml_tune_h_selection.json).", ""]
    for step in steps:
        lines.append(f"- `{step['criterion']}` : {', '.join(step['candidates'])}.")
    selected = next(s for s in summaries if s["config"] == chosen)
    xgb_depth = next(s for s in summaries if s["config"] == "xgb_depth4")
    cat_h = next(s for s in summaries if s["config"] == "cat_H")
    lines += ["", "## Compromis de la proposition", "",
              f"Face à CatBoost H, `{chosen}` change le F1 moyen de {selected['f1_mean']-cat_h['f1_mean']:+.4f}, les fraudes détectées de {selected['tp_total']-cat_h['tp_total']:+d} et les fausses alertes de {selected['fp_total']-cat_h['fp_total']:+d}. Face au candidat provisoire XGBoost profondeur 4, les écarts sont {selected['f1_mean']-xgb_depth['f1_mean']:+.4f} de F1 moyen, {selected['tp_total']-xgb_depth['tp_total']:+d} fraudes détectées et {selected['fp_total']-xgb_depth['fp_total']:+d} fausses alertes. Le F1 minimum est {selected['f1_min']:.4f} contre {xgb_depth['f1_min']:.4f}.", "",
              f"L'ajustement médian prend {selected['fit_seconds_median']:.2f} s contre {xgb_depth['fit_seconds_median']:.2f} s pour XGBoost profondeur 4, soit {selected['fit_seconds_median']/xgb_depth['fit_seconds_median']:.1f} fois plus dans ces exécutions locales. Les tailles médianes sont {selected['serialized_bytes_median']/2**20:.3f} et {xgb_depth['serialized_bytes_median']/2**20:.3f} Mio. La règle préannoncée ne fait intervenir le coût que si le F1 moyen et la régularité ne départagent pas les candidats. Elle propose donc la configuration ci-dessus, avec ce coût comme compromis explicite à discuter, sans la figer comme modèle final.", ""]
    lines += ["| Fenêtre | F1 XGBoost profondeur 4 | F1 proposition | Écart | TP écart | FP écart |",
              "| ---: | ---: | ---: | ---: | ---: | ---: |"]
    for a, b in zip(groups["xgb_depth4"], groups[chosen]):
        lines.append(f"| {a['fold']} | {a['f1']:.4f} | {b['f1']:.4f} | {b['f1']-a['f1']:+.4f} | {b['tp']-a['tp']:+d} | {b['fp']-a['fp']:+d} |")
    lines += ["", "Cette proposition attend la discussion avec l'utilisateur. Les seuils ont été réestimés sur chaque réserve interne ; les différences entre pipelines ne sont pas un effet causal isolé d'un paramètre. La signature PaySim montant/solde, l'heure simulée, les validations réutilisées et les labels du futur test vus pendant l'EDA limitent la portée des résultats. Aucun score du test 505 à 743 n'a été calculé. Aucun modèle de déploiement n'est produit.", ""]
    Path("docs/ML_TUNE_H_SELECTION.md").write_text("\n".join(lines))
    print("Sélection proposée :", chosen, steps)


if __name__ == "__main__":
    main()
