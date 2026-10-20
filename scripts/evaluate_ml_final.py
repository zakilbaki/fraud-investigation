"""Appliquer une seule fois le pipeline gelé au test réservé."""

import argparse
from pathlib import Path

from threadpoolctl import threadpool_limits

from fraud_investigation.ml_final_test import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("data/raw/PS_20174392719_1491204439457_log.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/ml_final_catboost"))
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        result = evaluate(args.csv, args.output)
    m = result["overall"]
    print(f"Test unique : {m['transactions']} transactions, {m['frauds']} fraudes ; "
          f"P={m['precision']}, R={m['recall']}, F1={m['f1']}")


if __name__ == "__main__":
    main()
