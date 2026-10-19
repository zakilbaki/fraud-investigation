"""Couverture de l'historique sortant strictement antérieur pour F."""

from __future__ import annotations

import polars as pl


def sender_step_history(frame: pl.DataFrame) -> pl.DataFrame:
    """Une ligne par (émetteur, step), avec effectif et cumul des steps précédents."""
    if frame.columns != ["step", "nameOrig"]:
        raise ValueError("Entrées attendues : step et nameOrig uniquement")
    if frame.null_count().to_numpy().sum() or frame["step"].min() < 1:
        raise ValueError("Step ou identifiant absent, ou step non positif")
    grouped = (frame.group_by("nameOrig", "step")
               .agg(pl.len().alias("transactions"))
               .sort("nameOrig", "step")
               .with_columns(
                   (pl.col("transactions").cum_sum().over("nameOrig", order_by="step")
                    - pl.col("transactions")).alias("prior_count")))
    return grouped


def step_coverage(grouped: pl.DataFrame) -> pl.DataFrame:
    """Agrégats pondérés par transactions, jamais par comptes distincts."""
    n = pl.col("transactions")
    h = pl.col("prior_count")
    result = grouped.group_by("step").agg(
        n.sum().alias("rows"),
        pl.when(h > 0).then(n).otherwise(0).sum().alias("nonzero_rows"),
        (n * h).sum().alias("sum_prior"),
        h.max().alias("max_prior"),
        *[pl.when(condition).then(n).otherwise(0).sum().alias(label)
          for label, condition in (
              ("count_0", h == 0),
              ("count_1", h == 1),
              ("count_2_4", (h >= 2) & (h <= 4)),
              ("count_5_9", (h >= 5) & (h <= 9)),
              ("count_10_plus", h >= 10),
          )],
    ).sort("step")
    assert (result["count_0"] + result["count_1"] + result["count_2_4"]
            + result["count_5_9"] + result["count_10_plus"]).sum() == result["rows"].sum()
    return result
