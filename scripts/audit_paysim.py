"""Audit descriptif hors ligne d'un CSV PaySim, sans modifier les lignes source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import polars as pl


NUMERIC_COLUMNS = (
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
)
LABEL_COLUMNS = ("isFraud", "isFlaggedFraud")
REQUIRED_COLUMNS = ("step", "type", "nameOrig", "nameDest", *NUMERIC_COLUMNS, *LABEL_COLUMNS)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_rows(frame: pl.LazyFrame) -> list[dict[str, object]]:
    return frame.collect(engine="streaming").to_dicts()


def audit(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)

    # Toute erreur de décodage ou de conversion fait échouer l'audit.
    frame = pl.scan_csv(path, infer_schema_length=10_000, null_values=[""])
    schema = frame.collect_schema()
    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(schema.names()))
    if missing_columns:
        raise ValueError(f"Colonnes PaySim absentes : {', '.join(missing_columns)}")

    numeric_types = {pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16,
                     pl.UInt32, pl.UInt64, pl.Float32, pl.Float64}
    for name in ("step", *NUMERIC_COLUMNS, *LABEL_COLUMNS):
        if schema[name] not in numeric_types:
            raise ValueError(f"Type numérique attendu pour {name}, reçu {schema[name]}")

    expressions = [pl.len().alias("row_count")]
    expressions += [pl.col(name).null_count().alias(f"null__{name}") for name in schema.names()]
    expressions += [
        pl.col("step").min().alias("step_min"),
        pl.col("step").max().alias("step_max"),
        (pl.col("step") <= 0).sum().alias("step_non_positive"),
    ]
    for name in NUMERIC_COLUMNS:
        expressions += [
            (pl.col(name) < 0).sum().alias(f"negative__{name}"),
            (pl.col(name) == 0).sum().alias(f"zero__{name}"),
            (~pl.col(name).cast(pl.Float64).is_finite()).sum().alias(f"non_finite__{name}"),
        ]
    for name in LABEL_COLUMNS:
        expressions.append(
            (~pl.col(name).is_in([0, 1])).sum().alias(f"invalid__{name}")
        )
    summary = collect_rows(frame.select(expressions))[0]

    return {
        "source_file": path.name,
        "source_size_bytes": path.stat().st_size,
        "source_sha256": sha256_file(path),
        "polars_version": pl.__version__,
        "columns": [{"name": name, "dtype": str(dtype)} for name, dtype in schema.items()],
        "row_count": summary["row_count"],
        "null_counts": {name: summary[f"null__{name}"] for name in schema.names()},
        "step": {
            "min": summary["step_min"],
            "max": summary["step_max"],
            "non_positive_count": summary["step_non_positive"],
            "distribution": collect_rows(
                frame.group_by("step").agg(pl.len().alias("count")).sort("step")
            ),
        },
        "types": collect_rows(
            frame.group_by("type").agg(pl.len().alias("count")).sort("type")
        ),
        "labels": {
            name: {
                "distribution": collect_rows(
                    frame.group_by(name).agg(pl.len().alias("count")).sort(name)
                ),
                "invalid_count": summary[f"invalid__{name}"],
            }
            for name in LABEL_COLUMNS
        },
        "numeric_checks": {
            name: {
                "negative_count": summary[f"negative__{name}"],
                "zero_count": summary[f"zero__{name}"],
                "non_finite_count": summary[f"non_finite__{name}"],
            }
            for name in NUMERIC_COLUMNS
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="CSV PaySim brut à inspecter")
    parser.add_argument("--output", type=Path, help="Rapport JSON local, exclu de Git")
    args = parser.parse_args()
    report = json.dumps(audit(args.csv), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Audit écrit dans {args.output}")
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
