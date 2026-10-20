"""Ajuster et sauvegarder le pipeline final avant le test."""

import argparse
from pathlib import Path

from threadpoolctl import threadpool_limits

from fraud_investigation.ml_final import freeze


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("data/raw/PS_20174392719_1491204439457_log.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/ml_final_catboost"))
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        result = freeze(args.csv, args.output)
    print(f"Pipeline gelé : seuil={result['threshold']:.12f}, "
          f"empreinte={result['pipeline_sha256']}")


if __name__ == "__main__":
    main()
