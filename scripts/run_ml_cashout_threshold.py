"""Choisir le seuil sur la réserve, puis comparer sur le test déjà évalué."""

import argparse
from pathlib import Path

from threadpoolctl import threadpool_limits

from fraud_investigation.ml_cashout_threshold import compare_on_test, select_on_reserve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("reserve", "test"))
    parser.add_argument("--csv", type=Path,
                        default=Path("data/raw/PS_20174392719_1491204439457_log.csv"))
    parser.add_argument("--model", type=Path,
                        default=Path("data/ml_final_catboost/pipeline.joblib"))
    parser.add_argument("--scores", type=Path,
                        default=Path("data/ml_final_catboost/test_predictions.npz"))
    reserve = Path("docs/results/ml_cashout_threshold_reserve.json")
    test = Path("docs/results/ml_cashout_threshold_test.json")
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        if args.phase == "reserve":
            result = select_on_reserve(args.csv, args.model, reserve)
            print(f"Seuil CASH_OUT sur 361–432 : {result['cash_out_threshold']}")
        else:
            result = compare_on_test(args.csv, args.model, args.scores, reserve, test)
            print(f"Test exploratoire : {result['overall']['delta']}")


if __name__ == "__main__":
    main()
