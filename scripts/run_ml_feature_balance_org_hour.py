"""Exécuter un modèle et une fenêtre de l'expérience D."""

import argparse
from pathlib import Path

from threadpoolctl import threadpool_limits

from fraud_investigation.ml_benchmark import write_result
from fraud_investigation.ml_feature_balance_org_hour import MODELS, run_one


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=MODELS)
    parser.add_argument("--fold", required=True, type=int, choices=range(1, 6))
    parser.add_argument("--csv", type=Path, default=Path("data/raw/PS_20174392719_1491204439457_log.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/ml_feature_balance_org_hour"))
    args = parser.parse_args()
    destination = args.output / f"{args.model}_fold_{args.fold}.json"
    if destination.exists():
        print(f"Déjà présent : {destination}", flush=True)
        return
    with threadpool_limits(limits=4):
        result = run_one(args.csv, args.model, args.fold)
    write_result(destination, result)
    print(f"{args.model} fenêtre {args.fold}: F1={result['f1']:.6f}, "
          f"précision={result['precision']}, rappel={result['recall']:.6f}, "
          f"temps={result['total_seconds']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
