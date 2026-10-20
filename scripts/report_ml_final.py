"""Vérifier l'évaluation unique et produire rapport, fiche modèle et figures."""

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(".cache/matplotlib").resolve()))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fraud_investigation.ml_final import CSV_SHA256, MODEL_COLUMNS, sha256
from fraud_investigation.ml_final_test import AMOUNT_BUCKETS, PERIODS, TEST_FRAUDS, TEST_ROWS


def fmt(value, digits=4):
    return "n.d." if value is None else f"{value:.{digits}f}"


def intfmt(value):
    return f"{value:,}".replace(",", " ")


def table(headers, rows):
    return ["| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] + ["---:"] * (len(headers)-1)) + " |",
            *["| " + " | ".join(str(x) for x in row) + " |" for row in rows]]


def check_metrics(row):
    assert row["tp"] + row["fn"] == row["frauds"]
    assert row["tn"] + row["fp"] == row["transactions"] - row["frauds"]
    assert row["alerts"] == row["tp"] + row["fp"]
    if row["transactions"]:
        assert row["prevalence"] == row["frauds"] / row["transactions"]
    else:
        assert row["prevalence"] is None
    assert row["precision"] == (row["tp"] / row["alerts"] if row["alerts"] else None)
    assert row["recall"] == (row["tp"] / row["frauds"] if row["frauds"] else None)
    denominator = 2*row["tp"] + row["fp"] + row["fn"]
    expected_f1 = 2*row["tp"] / denominator if denominator else (0.0 if row["transactions"] else None)
    assert row["f1"] == expected_f1


def main():
    manifest = json.loads(Path("docs/results/ml_final_manifest.json").read_text())
    result = json.loads(Path("docs/results/ml_final_test.json").read_text())
    selected = json.loads(Path("docs/results/ml_tune_h_selection.json").read_text())
    assert sha256("data/raw/PS_20174392719_1491204439457_log.csv") == CSV_SHA256
    assert manifest["csv_sha256"] == result["csv_sha256"] == selected["source_sha256"] == CSV_SHA256
    assert manifest["pipeline_sha256"] == result["pipeline_sha256"]
    assert sha256("data/ml_final_catboost/pipeline.joblib") == manifest["pipeline_sha256"]
    assert manifest["predictor_columns"] == list(MODEL_COLUMNS)
    assert manifest["fit_steps"] == [1, 360] and manifest["threshold_steps"] == [361, 432]
    assert result["test_steps"] == [505, 743] and result["history_initialization_steps"] == [1, 504]
    assert result["threshold"] == manifest["threshold"]
    assert result["history_first_step_verified"] and result["status"] == "single_final_test"
    assert selected["selection"]["proposed"] == result["model_config"] == "cat_slow200"
    overall = result["overall"]
    assert (overall["transactions"], overall["frauds"]) == (TEST_ROWS, TEST_FRAUDS)
    check_metrics(overall)
    for key, expected in (("by_type", 5), ("by_amount", 6), ("by_period", 3)):
        groups = result[key]
        assert len(groups) == expected
        for row in groups.values():
            check_metrics(row)
        for field in ("transactions", "frauds", "alerts", "tp", "fp", "fn", "tn"):
            assert sum(row[field] for row in groups.values()) == overall[field]
    assert list(result["by_amount"]) == list(AMOUNT_BUCKETS)
    assert list(result["by_period"]) == [f"{a}-{b}" for a, b in PERIODS]
    last = result["by_period"]["721-743"]
    assert last["frauds"] == last["transactions"] == 272 and last["tn"] == last["fp"] == 0
    assert result["by_amount"]["0"]["frauds"] == result["by_amount"]["0"]["fn"] == 10
    # Seules les prédictions locales servent à vérifier le résultat agrégé.
    with np.load("data/ml_final_catboost/test_predictions.npz") as local:
        score, alert, label, step = (local[k] for k in ("score", "alert", "label", "step"))
        assert len(score) == TEST_ROWS and int(label.sum()) == TEST_FRAUDS
        assert int(step.min()) == 505 and int(step.max()) == 743
        assert np.array_equal(alert, score >= manifest["threshold"])
        assert int((alert & (label == 1)).sum()) == overall["tp"]
        assert int((alert & (label == 0)).sum()) == overall["fp"]
        assert int((~alert & (label == 1)).sum()) == overall["fn"]
        assert int((~alert & (label == 0)).sum()) == overall["tn"]
    validation = next(s for s in selected["candidates"] if s["config"] == "cat_slow200")
    figure_dir = Path("docs/figures")
    plt.rcParams.update({"font.size": 10})

    fig, ax = plt.subplots(figsize=(8, 4))
    positions = np.arange(3)
    ax.bar(positions-.19, [validation[f"{m}_mean"] for m in ("precision", "recall", "f1")],
           width=.38, label="Moyenne des 5 validations")
    ax.bar(positions+.19, [overall[m] for m in ("precision", "recall", "f1")],
           width=.38, label="Test global")
    ax.set_xticks(positions, ["Précision", "Rappel", "F1"])
    ax.set_ylim(0, 1); ax.set_ylabel("Métrique")
    ax.legend(loc="upper center", bbox_to_anchor=(.5, 1.14), ncol=2)
    ax.grid(axis="y", alpha=.2)
    fig.tight_layout(); fig.savefig(figure_dir/"ml_final_test_comparison.png", dpi=150); plt.close(fig)

    fraud_types = ["CASH_OUT", "TRANSFER"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    rows = [result["by_type"][name] for name in fraud_types]
    x = np.arange(2)
    axes[0].bar(x, [r["tp"] for r in rows], label="Fraudes détectées")
    axes[0].bar(x, [r["fn"] for r in rows], bottom=[r["tp"] for r in rows], label="Fraudes manquées")
    axes[0].set_xticks(x, fraud_types); axes[0].set_ylabel("Fraudes")
    axes[0].legend(loc="upper center", bbox_to_anchor=(.5, 1.16), ncol=2)
    axes[1].bar(x, [r["fp"] for r in rows], color="#bb6644")
    axes[1].set_xticks(x, fraud_types); axes[1].set_ylabel("Fausses alertes")
    fig.tight_layout(); fig.savefig(figure_dir/"ml_final_test_types.png", dpi=150); plt.close(fig)

    amount_rows = list(result["by_amount"].values())
    x = np.arange(len(AMOUNT_BUCKETS))
    fig, axes = plt.subplots(1, 2, figsize=(14, 4))
    axes[0].bar(x, [r["transactions"] for r in amount_rows])
    axes[0].set_yscale("symlog", linthresh=1)
    axes[0].set_ylabel("Transactions, échelle symlog")
    axes[1].bar(x, [r["tp"] for r in amount_rows], label="Détectées")
    axes[1].bar(x, [r["fn"] for r in amount_rows], bottom=[r["tp"] for r in amount_rows], label="Manquées")
    axes[1].set_ylabel("Fraudes, effectifs linéaires"); axes[1].legend()
    for ax in axes:
        ax.set_xticks(x, AMOUNT_BUCKETS, rotation=30, ha="right")
    fig.tight_layout(); fig.savefig(figure_dir/"ml_final_test_amount.png", dpi=150); plt.close(fig)

    period_rows = list(result["by_period"].values())
    periods = list(result["by_period"])
    x = np.arange(3)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    axes[0].bar(x, [r["transactions"] for r in period_rows]); axes[0].set_ylabel("Transactions")
    axes[0].set_yscale("symlog", linthresh=1)
    axes[1].bar(x, [r["tp"] for r in period_rows], label="Détectées")
    axes[1].bar(x, [r["fn"] for r in period_rows], bottom=[r["tp"] for r in period_rows], label="Manquées")
    axes[1].set_ylabel("Fraudes"); axes[1].legend()
    axes[2].bar(x, [100*r["prevalence"] for r in period_rows]); axes[2].set_ylabel("Taux de fraude, %")
    for ax in axes:
        ax.set_xticks(x, periods, rotation=20)
    fig.tight_layout(); fig.savefig(figure_dir/"ml_final_test_periods.png", dpi=150); plt.close(fig)

    lines = ["# Lot 4.5 : évaluation finale du pipeline gelé", "",
             "La [décision](ML_FINAL_FREEZE.md) et le [manifeste](results/ml_final_manifest.json) ont été publiés avant le score. Le modèle CatBoost `cat_slow200` apprend sur 1–360 et le seuil est fixé sur 361–432. La période 433–504 a participé à la sélection antérieure, sans réajustement. Le test 505–743 est évalué en un ensemble unique, une fois après gel. Les labels ne construisent ni variables ni historiques.", "",
             "## Résultat global", "",
             f"**{intfmt(overall['transactions'])} transactions**, **{intfmt(overall['frauds'])} fraudes**, taux de fraude **{100*overall['prevalence']:.4f} %**. Seuil fixé **{manifest['threshold']:.12f}**. **{intfmt(overall['alerts'])} alertes**, précision **{overall['precision']:.4f}**, rappel **{overall['recall']:.4f}**, F1 **{overall['f1']:.4f}**.", "",
             "Matrice de confusion, lignes = label réel, colonnes = décision :", "",
             "| Réel / décision | Normale | Alerte fraude |", "| --- | ---: | ---: |",
             f"| Normale | TN {intfmt(overall['tn'])} | FP {intfmt(overall['fp'])} |",
             f"| Fraude | FN {intfmt(overall['fn'])} | TP {intfmt(overall['tp'])} |", "",
             "Le taux de fraude est `fraudes / transactions`. La précision est `TP / alertes`, le rappel est `TP / fraudes` et F1 est `2TP / (2TP + FP + FN)`. Le score brut n'est pas présenté comme une probabilité calibrée.", "",
             "## Comparaison descriptive avec la validation", "",
             "| Ensemble | Précision | Rappel | F1 | Nature |", "| --- | ---: | ---: | ---: | --- |",
             f"| Cinq validations | {validation['precision_mean']:.4f} | {validation['recall_mean']:.4f} | {validation['f1_mean']:.4f} | Moyenne arithmétique des cinq fenêtres |",
             f"| Test 505–743 | {overall['precision']:.4f} | {overall['recall']:.4f} | {overall['f1']:.4f} | Métriques globales sur une seule période |", "",
             "Ces deux lignes n'ont pas le même dénominateur ni les mêmes prévalences. Les validations ont guidé plusieurs choix ; le test avait été vu en EDA par l'analyste, même si ses scores n'ont pas servi aux choix.", "",
             "![Métriques validation et test](figures/ml_final_test_comparison.png)", "",
             "## Diagnostics préannoncés par type", ""]
    lines += table(["Type", "Transactions", "Fraudes", "Taux fraude %", "Alertes", "TP", "FP", "FN", "Précision", "Rappel", "F1"],
                   [[name, r["transactions"], r["frauds"], fmt(100*r["prevalence"], 3), r["alerts"],
                     r["tp"], r["fp"], r["fn"], fmt(r["precision"]), fmt(r["recall"]), fmt(r["f1"])]
                    for name, r in result["by_type"].items()])
    lines += ["", "![Fraudes et fausses alertes par type](figures/ml_final_test_types.png)", "",
              "Les fraudes test sont dans CASH_OUT et TRANSFER. Le rappel diffère fortement entre ces types. Pour un type sans fraude, le rappel est non défini ; une précision sans alerte est aussi non définie. Le F1 nul indiqué par la fonction pour ces groupes sans positif ne mesure pas une capacité à détecter des fraudes.", "",
              "## Diagnostics préannoncés par montant", "",
              "Les bornes positives sont des unions des tranches de largeur 0,5 de `log10(amount)` employées dans l'EDA. Le zéro est isolé. `10^5,5 ≈ 316 227,77` et `10^6,5 ≈ 3 162 277,66` unités PaySim. Chaque borne inférieure positive est incluse ; la borne supérieure est exclue.", ""]
    lines += table(["Montant PaySim", "Transactions", "Fraudes", "Taux fraude %", "TP", "FP", "FN", "Précision", "Rappel"],
                   [[name, r["transactions"], r["frauds"], fmt(100*r["prevalence"], 3), r["tp"], r["fp"],
                     r["fn"], fmt(r["precision"]), fmt(r["recall"])]
                    for name, r in result["by_amount"].items()])
    lines += ["", "![Volumes et fraudes par tranche de montant](figures/ml_final_test_amount.png)", "",
              "L'axe des volumes utilise `symlog` pour rendre visibles 10 montants nuls face aux grandes tranches ; l'axe des fraudes est linéaire. Les 10 montants nuls sont tous frauduleux et tous manqués dans ce test. Les performances parfaites des deux plus grandes tranches décrivent une signature du simulateur, pas une règle transférable au réel.", "",
              "## Diagnostics préannoncés par période", ""]
    lines += table(["Steps", "Transactions", "Fraudes", "Taux fraude %", "Alertes", "TP", "FP", "FN", "Précision", "Rappel", "F1"],
                   [[name, r["transactions"], r["frauds"], fmt(100*r["prevalence"], 3), r["alerts"],
                     r["tp"], r["fp"], r["fn"], fmt(r["precision"]), fmt(r["recall"]), fmt(r["f1"])]
                    for name, r in result["by_period"].items()])
    lines += ["", "![Volume et fraude par période](figures/ml_final_test_periods.png)", "",
              "Le volume est en échelle `symlog`, les fraudes et le taux en axes linéaires distincts. Les steps 721–743 comptent 272 transactions, toutes frauduleuses : 223 alertées et 49 manquées. Il n'y a aucune transaction normale dans cette tranche ; taux de faux positifs, ROC-AUC et séparation des deux classes n'y sont pas définissables. Elle reste incluse dans le test global.", "",
              "## Vérifications et limites", "",
              "L'empreinte du CSV et celle du pipeline rechargé correspondent au manifeste antérieur au test. À la frontière 504/505, un destinataire inédit reçoit zéro ; chaque step est prédit avant mise à jour de son historique. Les matrices de confusion et les regroupements retrouvent les 298 584 lignes et 2 592 fraudes. Les prédictions individuelles et labels restent uniquement dans `data/ml_final_catboost/`, ignoré par Git.", "",
              "La première tentative s'est arrêtée avant tout score test : un contrôle utilisait un accès direct au dictionnaire pour un destinataire inédit. La trace locale est conservée. La correction a remplacé cet accès par zéro, déjà utilisé par la construction effective du compteur ; le modèle, son empreinte et son seuil sont restés identiques. La seconde tentative a produit cette unique évaluation complète.", "",
              "PaySim est synthétique ; le rapport montant/solde est une signature forte de ce simulateur. L'heure est conventionnelle, la disponibilité des soldes et historiques en situation réelle n'est pas établie, et les validations ont été réutilisées. L'EDA avait exposé les labels du test. Ces limites empêchent d'annoncer une performance garantie sur des transactions réelles. Aucun réglage n'a été lancé après le score.", ""]
    Path("docs/ML_FINAL_REPORT.md").write_text("\n".join(lines))

    card = ["# Fiche du modèle CatBoost PaySim, lot 4.5", "",
            "## Usage visé", "",
            "Prototype pédagogique de classement de transactions PaySim pour investigation. Le score déclenche une alerte selon un seuil fixé ; sa calibration comme probabilité fiable n'a pas été évaluée. Aucun déploiement ou usage réel n'est validé.", "",
            "## Entrées et état nécessaire", "",
            "`type`, `amount`, `oldbalanceOrg`, heure cyclique simulée, ratio montant/solde et nombre de réceptions antérieures du destinataire. Les sept colonnes finales et leur ordre sont dans le [manifeste](results/ml_final_manifest.json). Pour une prédiction, l'application devrait disposer des transactions précédentes par `nameDest` et mettre à jour ce compteur après avoir prédit tout le step. Un nouveau destinataire reçoit zéro. Le solde nul donne un ratio manquant. Aucun label, identifiant brut ou solde après transaction n'entre dans le modèle.", "",
            "## Ajustement et seuil", "",
            f"CatBoost CPU, 200 itérations, pas 0,05, profondeur 6, graine 42. Ajustement sur steps 1–360 ; seuil F1 maximal **{manifest['threshold']:.12f}** sur 361–432, avec scores égaux groupés et seuil le plus haut à égalité. Aucun ajustement sur 433–504. Pipeline local sauvegardé et rechargé avant le test ; empreintes et versions dans le manifeste.", "",
            "## Mesure réservée", "",
            f"Sur steps 505–743 : {TEST_ROWS} transactions, {TEST_FRAUDS} fraudes, {overall['alerts']} alertes, {overall['tp']} TP, {overall['fp']} FP, {overall['fn']} FN et {overall['tn']} TN. Précision {overall['precision']:.4f}, rappel {overall['recall']:.4f}, F1 {overall['f1']:.4f}. Voir le [rapport final](ML_FINAL_REPORT.md) pour les dénominateurs et diagnostics.", "",
            "## Limites", "",
            "PaySim est un simulateur. Le ratio montant/solde et les dernières périodes portent des signatures artificielles possibles. L'heure ne correspond pas à un calendrier civil connu. Les validations temporelles ont été réutilisées pour les choix ; les labels du futur test avaient été examinés pendant l'EDA. La disponibilité et la qualité en temps réel des soldes et historiques ne sont pas démontrées. Le test a une période entièrement frauduleuse. Aucun résultat ne garantit une généralisation réelle.", ""]
    Path("docs/ML_MODEL_CARD.md").write_text("\n".join(card))
    print("Rapport final et fiche modèle : agrégats, prédictions locales et figures vérifiés")


if __name__ == "__main__":
    main()
