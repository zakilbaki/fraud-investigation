"""Historique des réceptions strictement antérieures, sans labels."""

from __future__ import annotations

import polars as pl


BUCKETS = (
    ("count_0", lambda h: h == 0),
    ("count_1", lambda h: h == 1),
    ("count_2_4", lambda h: (h >= 2) & (h <= 4)),
    ("count_5_9", lambda h: (h >= 5) & (h <= 9)),
    ("count_10_19", lambda h: (h >= 10) & (h <= 19)),
    ("count_20_49", lambda h: (h >= 20) & (h <= 49)),
    ("count_50_99", lambda h: (h >= 50) & (h <= 99)),
    ("count_100_499", lambda h: (h >= 100) & (h <= 499)),
    ("count_500_999", lambda h: (h >= 500) & (h <= 999)),
    ("count_1000_plus", lambda h: h >= 1000),
)


def recipient_step_history(frame: pl.DataFrame) -> pl.DataFrame:
    """Une ligne par (destinataire, step) avec cumul des steps précédents."""
    if frame.columns != ["step", "nameDest"]:
        raise ValueError("Entrées attendues : step et nameDest uniquement")
    if frame.is_empty() or frame.null_count().to_numpy().sum() or frame["step"].min() < 1:
        raise ValueError("Entrée vide, absente ou step non positif")
    return (frame.group_by("nameDest", "step")
            .agg(pl.len().alias("transactions"))
            .sort("nameDest", "step")
            .with_columns(
                (pl.col("transactions").cum_sum().over("nameDest", order_by="step")
                 - pl.col("transactions")).alias("prior_count")))


def recipient_step_coverage(grouped: pl.DataFrame) -> pl.DataFrame:
    """Distribution pondérée par transactions pour chaque step."""
    n = pl.col("transactions")
    h = pl.col("prior_count")
    result = grouped.group_by("step").agg(
        n.sum().alias("rows"),
        pl.when(h > 0).then(n).otherwise(0).sum().alias("nonzero_rows"),
        (n * h).sum().alias("sum_prior"),
        h.max().alias("max_prior"),
        *[pl.when(condition(h)).then(n).otherwise(0).sum().alias(label)
          for label, condition in BUCKETS],
    ).sort("step")
    assert sum(result[label] for label, _ in BUCKETS).sum() == result["rows"].sum()
    return result


def counts_for_rows(frame: pl.DataFrame) -> pl.Series:
    """Rattacher le compteur vérifié à chaque ligne dans son ordre original."""
    if not {"step", "nameDest"}.issubset(frame.columns):
        raise ValueError("step et nameDest requis")
    grouped = recipient_step_history(frame.select("step", "nameDest"))
    joined = (frame.select("step", "nameDest")
              .with_row_index("row_index")
              .join(grouped.select("step", "nameDest", "prior_count"),
                    on=["step", "nameDest"], how="left", validate="m:1")
              .sort("row_index"))
    assert joined.height == frame.height
    assert joined["prior_count"].null_count() == 0
    assert (joined["row_index"].min() == 0
            and joined["row_index"].max() == frame.height - 1
            and joined["row_index"].is_sorted())
    return joined["prior_count"]
