"""Analyse exploratoire après test : seuil CASH_OUT sans réentraînement."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import polars as pl

from fraud_investigation.ml_benchmark import metrics, scores
from fraud_investigation.ml_final import MODEL_COLUMNS, arrays, sha256
from fraud_investigation.ml_recipient_history import counts_for_rows


def selected_threshold(label, score, global_threshold):
    """F1 CASH_OUT maximal sous le seuil global, scores égaux groupés."""
    label, score = np.asarray(label), np.asarray(score)
    if len(label) == 0 or len(label) != len(score) or not np.isfinite(score).all():
        raise ValueError("Scores et labels de réserve invalides")
    if not np.isin(label, [0, 1]).all() or label.min() == label.max():
        raise ValueError("Les deux classes sont nécessaires")
    order = np.argsort(-score, kind="stable")
    ordered_score, ordered_label = score[order], label[order]
    last = np.r_[np.flatnonzero(np.diff(ordered_score)), len(score) - 1]
    tp = np.cumsum(ordered_label, dtype=np.int64)[last]
    alerts = last + 1
    baseline = metrics(label, score, global_threshold)
    best_threshold = float(global_threshold)
    best_tp, best_denom = baseline["tp"], baseline["alerts"] + baseline["frauds"]
    # Parcours décroissant : à F1 égal, le premier seuil est le plus élevé.
    for index in np.flatnonzero(ordered_score[last] < global_threshold):
        current_tp, current_denom = int(tp[index]), int(alerts[index] + baseline["frauds"])
        if current_tp * best_denom > best_tp * current_denom:
            best_threshold = float(ordered_score[last[index]])
            best_tp, best_denom = current_tp, current_denom
    return best_threshold


def decision_metrics(label, decision):
    """Même définition que le benchmark, pour des seuils dépendant du type."""
    label, decision = np.asarray(label), np.asarray(decision, dtype=bool)
    if len(label) == 0 or len(label) != len(decision) or not np.isin(label, [0, 1]).all():
        raise ValueError("Décisions et labels invalides")
    tp = int(np.count_nonzero(decision & (label == 1)))
    fp = int(np.count_nonzero(decision & (label == 0)))
    fn = int(np.count_nonzero(~decision & (label == 1)))
    tn = int(np.count_nonzero(~decision & (label == 0)))
    n, frauds, alerts = len(label), tp + fn, tp + fp
    return {"transactions": n, "frauds": frauds, "prevalence": frauds / n,
            "alerts": alerts, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / alerts if alerts else None,
            "recall": tp / frauds if frauds else None,
            "f1": 2 * tp / (alerts + frauds) if alerts + frauds else 0.0}


def artifacts(csv_path, model_path):
    manifest = json.loads(Path("docs/results/ml_final_manifest.json").read_text())
    final = json.loads(Path("docs/results/ml_final_test.json").read_text())
    assert sha256(csv_path) == manifest["csv_sha256"] == final["csv_sha256"]
    assert sha256(model_path) == manifest["pipeline_sha256"] == final["pipeline_sha256"]
    assert manifest["fit_steps"] == [1, 360] and manifest["threshold_steps"] == [361, 432]
    assert manifest["test_steps"] == final["test_steps"] == [505, 743]
    assert manifest["predictor_columns"] == list(MODEL_COLUMNS)
    frozen = joblib.load(model_path)
    assert frozen["threshold"] == manifest["threshold"] == final["threshold"]
    assert frozen["features"].columns == list(MODEL_COLUMNS)
    assert frozen["model"].get_params() == manifest["model_parameters"]
    return manifest, final, frozen


def select_on_reserve(csv_path, model_path, output_path):
    """Ne lit aucune ligne du test pour le choix du seuil."""
    if Path(output_path).exists():
        raise FileExistsError(output_path)
    manifest, _, frozen = artifacts(csv_path, model_path)
    frame = (pl.scan_csv(csv_path).filter(pl.col("step") <= 432)
             .select("step", "type", "amount", "oldbalanceOrg", "nameDest", "isFraud")
             .collect())
    assert frame.height == manifest["fit_rows"] + manifest["threshold_rows"]
    assert frame.null_count().to_numpy().sum() == 0
    step, kind, amount, balance = arrays(frame)
    prior = counts_for_rows(frame.select("step", "nameDest")).to_numpy().astype(np.float32)
    label = frame["isFraud"].to_numpy().astype(np.uint8)
    reserve = (step >= 361) & (step <= 432)
    assert (int(reserve.sum()), int(label[reserve].sum())) == (822359, 840)
    cash = reserve & frame["type"].eq("CASH_OUT").to_numpy()
    x = frozen["features"].transform(kind[cash], amount[cash], balance[cash],
                                      step[cash], prior[cash])
    assert list(x.columns) == list(MODEL_COLUMNS)
    cash_score = scores(frozen["model"], x)
    global_threshold = manifest["threshold"]
    chosen = selected_threshold(label[cash], cash_score, global_threshold)
    baseline = metrics(label[cash], cash_score, global_threshold)
    variant = metrics(label[cash], cash_score, chosen)
    assert chosen <= global_threshold and variant["f1"] >= baseline["f1"]
    result = {"status": "exploratory_threshold_selected_on_reserve",
              "csv_sha256": manifest["csv_sha256"],
              "pipeline_sha256": manifest["pipeline_sha256"],
              "model_config": manifest["model_config"],
              "fit_steps": [1, 360], "threshold_steps": [361, 432],
              "reserve_rows": int(reserve.sum()), "reserve_frauds": int(label[reserve].sum()),
              "cash_out_threshold": chosen, "global_threshold": global_threshold,
              "cash_out_reserve_global": baseline, "cash_out_reserve_variant": variant,
              "rule": "maximum CASH_OUT F1 at distinct scores <= global threshold; highest threshold on tie"}
    Path(output_path).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def compare_on_test(csv_path, model_path, predictions_path, reserve_path, output_path):
    """Réutilise les scores locaux du test et publie uniquement des agrégats."""
    if Path(output_path).exists():
        raise FileExistsError(output_path)
    manifest, final, _ = artifacts(csv_path, model_path)
    reserve = json.loads(Path(reserve_path).read_text())
    assert reserve["csv_sha256"] == manifest["csv_sha256"]
    assert reserve["pipeline_sha256"] == manifest["pipeline_sha256"]
    assert reserve["threshold_steps"] == [361, 432]
    assert reserve["global_threshold"] == manifest["threshold"]
    chosen, global_threshold = reserve["cash_out_threshold"], manifest["threshold"]
    assert chosen <= global_threshold
    attempt = json.loads(Path(predictions_path).with_name("test_attempt.json").read_text())
    assert attempt["state"] == "completed" and attempt["pipeline_sha256"] == manifest["pipeline_sha256"]
    with np.load(predictions_path) as saved:
        assert set(saved.files) == {"score", "alert", "label", "step"}
        prediction_score = saved["score"]
        saved_alert, label, step = saved["alert"], saved["label"], saved["step"]
    assert len(prediction_score) == final["overall"]["transactions"]
    assert np.isfinite(prediction_score).all() and ((prediction_score >= 0) & (prediction_score <= 1)).all()
    assert np.array_equal(saved_alert, prediction_score >= global_threshold)
    frame = (pl.scan_csv(csv_path).filter(pl.col("step") >= 505)
             .select("step", "type", "isFraud").collect())
    assert frame.height == len(label) and frame["step"].min() == 505 and frame["step"].max() == 743
    assert np.array_equal(step, frame["step"].to_numpy())
    assert np.array_equal(label, frame["isFraud"].to_numpy())
    cash = frame["type"].eq("CASH_OUT").to_numpy()
    assert decision_metrics(label, saved_alert) == final["overall"]
    assert decision_metrics(label[cash], saved_alert[cash]) == final["by_type"]["CASH_OUT"]
    variant_alert = np.where(cash, prediction_score >= chosen, saved_alert)
    assert np.array_equal(variant_alert[~cash], saved_alert[~cash])
    assert not np.any(saved_alert & ~variant_alert)
    variant_cash = decision_metrics(label[cash], variant_alert[cash])
    variant_overall = decision_metrics(label, variant_alert)
    baseline_cash = final["by_type"]["CASH_OUT"]
    baseline_overall = final["overall"]
    fields = ("alerts", "tp", "fp", "fn", "tn", "precision", "recall", "f1")
    delta = lambda base, new: {name: new[name] - base[name] for name in fields}
    assert variant_overall["tp"] - baseline_overall["tp"] == variant_cash["tp"] - baseline_cash["tp"]
    assert variant_overall["fp"] - baseline_overall["fp"] == variant_cash["fp"] - baseline_cash["fp"]
    result = {"status": "post_final_test_exploratory_only",
              "csv_sha256": manifest["csv_sha256"], "pipeline_sha256": manifest["pipeline_sha256"],
              "saved_scores_sha256": sha256(predictions_path),
              "saved_scores_reproduced_final_metrics": True,
              "ordered_steps_and_labels_match_csv": True, "other_type_decisions_unchanged": True,
              "threshold_steps": [361, 432], "test_steps": [505, 743],
              "global_threshold": global_threshold, "cash_out_threshold": chosen,
              "cash_out": {"global": baseline_cash, "variant": variant_cash,
                           "delta": delta(baseline_cash, variant_cash)},
              "overall": {"global": baseline_overall, "variant": variant_overall,
                          "delta": delta(baseline_overall, variant_overall)}}
    Path(output_path).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result
