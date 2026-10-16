"""Importer PaySim dans une base applicative et un fichier de labels séparé."""

from __future__ import annotations

import argparse
from pathlib import Path

from fraud_investigation.importer import import_paysim


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--database", type=Path, default=Path("data/app/fraud.sqlite"))
    parser.add_argument("--labels", type=Path, default=Path("data/evaluation/labels.sqlite"))
    parser.add_argument("--expected-sha256")
    parser.add_argument("--batch-size", type=int, default=20_000)
    args = parser.parse_args()
    result = import_paysim(
        args.csv, args.database, args.labels,
        expected_sha256=args.expected_sha256, batch_size=args.batch_size,
    )
    print(
        f"status={result.status} transactions={result.transactions} "
        f"accounts={result.accounts} labels={result.labels} "
        f"source_sha256={result.source_sha256}"
    )


if __name__ == "__main__":
    main()
