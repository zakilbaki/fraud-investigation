"""Contrats ciblés de l'expérience B, sans relire le CSV PaySim."""

import unittest

import numpy as np

from fraud_investigation.ml_benchmark import FOLDS, TYPES, Features
from fraud_investigation.ml_feature_balance_org import BalanceFeatures, SOURCE_COLUMNS


class BalanceOrgExperimentTests(unittest.TestCase):
    def test_source_projection_and_chronology(self):
        self.assertEqual(SOURCE_COLUMNS, ("step", "type", "amount", "oldbalanceOrg", "isFraud"))
        for fit_end, reserve_end, val_end in FOLDS:
            self.assertEqual(reserve_end - fit_end, 72)
            self.assertEqual(val_end - reserve_end, 72)
            self.assertLess(val_end, 505)

    def test_feature_columns_and_baseline_prefix(self):
        kind = np.array([0, 1, 4, 3], dtype=np.uint8)
        amount = np.array([0, 10, 100, 1_000], dtype=np.float32)
        balance = np.array([0, 20, 200, 2_000], dtype=np.float32)
        forbidden = {"isFraud", "isFlaggedFraud", "step", "hour_sin", "hour_cos",
                     "oldbalanceDest", "newbalanceOrig", "newbalanceDest",
                     "nameOrig", "nameDest"}
        for name in ("xgboost", "catboost", "extra_trees", "random_forest", "knn"):
            features = BalanceFeatures(name).fit(kind[:2], amount[:2], balance[:2])
            x = features.transform(kind, amount, balance)
            self.assertFalse(forbidden.intersection(features.columns))
            self.assertEqual(len(features.columns), 3 if name == "catboost" else len(TYPES) + 2)
            reference = Features(name).fit(kind[:2], amount[:2]).transform(kind, amount)
            if name == "catboost":
                self.assertEqual(list(x.columns), features.columns)
                np.testing.assert_array_equal(x[["type", "amount"]].to_numpy(),
                                              reference.to_numpy())
                np.testing.assert_array_equal(x["oldbalanceOrg"].to_numpy(), balance)
            else:
                np.testing.assert_array_equal(x[:, :-1], reference)
                if name != "knn":
                    np.testing.assert_array_equal(x[:, -1], balance)
        self.assertAlmostEqual(float(features.balance_scaler.mean_[0]),
                               float(np.log1p(balance[:2]).mean()), places=5)
        self.assertNotAlmostEqual(float(features.balance_scaler.mean_[0]),
                                  float(np.log1p(balance).mean()), places=5)

    def test_invalid_balance_rejected(self):
        features = BalanceFeatures("knn").fit(np.array([0], dtype=np.uint8),
                                               np.array([1], dtype=np.float32),
                                               np.array([0], dtype=np.float32))
        with self.assertRaises(AssertionError):
            features.transform(np.array([0], dtype=np.uint8),
                               np.array([1], dtype=np.float32),
                               np.array([-1], dtype=np.float32))


if __name__ == "__main__":
    unittest.main()
