"""Contrats synthétiques de E sans lecture de PaySim."""

import unittest

import numpy as np

from fraud_investigation.ml_feature_balance_org_hour import CombinedFeatures
from fraud_investigation.ml_feature_balance_share import ShareFeatures, balance_share


class BalanceShareTests(unittest.TestCase):
    def test_ratio_defined_missing_and_above_one(self):
        amount = np.array([10, 3, 0, 20], dtype=np.float32)
        balance = np.array([20, 0, 0, 5], dtype=np.float32)
        result = balance_share(amount, balance)
        self.assertEqual(result[0], .5)
        self.assertTrue(np.isnan(result[1]))
        self.assertTrue(np.isnan(result[2]))
        self.assertEqual(result[3], 4)
        self.assertFalse(np.isinf(result).any())

    def test_only_ratio_added_to_d_for_both_models(self):
        kind = np.array([0, 1, 4, 3], dtype=np.uint8)
        amount = np.array([10, 3, 0, 20], dtype=np.float32)
        balance = np.array([20, 0, 0, 5], dtype=np.float32)
        step = np.array([1, 2, 24, 25], dtype=np.int16)
        forbidden = {"step", "isFraud", "isFlaggedFraud", "nameOrig", "nameDest",
                     "oldbalanceDest", "newbalanceOrig", "newbalanceDest"}
        for name in ("xgboost", "catboost"):
            e = ShareFeatures(name).fit(kind[:2], amount[:2], balance[:2])
            d = CombinedFeatures(name).fit(kind[:2], amount[:2], balance[:2])
            self.assertEqual(e.columns, [*d.columns, "part_solde"])
            self.assertFalse(forbidden.intersection(e.columns))
            x = e.transform(kind, amount, balance, step)
            prior = d.transform(kind, amount, balance, step)
            if name == "catboost":
                self.assertEqual(list(x.columns), e.columns)
                np.testing.assert_array_equal(x[d.columns].to_numpy(), prior.to_numpy())
                ratio = x["part_solde"].to_numpy()
            else:
                np.testing.assert_array_equal(x[:, :-1], prior)
                ratio = x[:, -1]
            np.testing.assert_equal(ratio, balance_share(amount, balance))


if __name__ == "__main__":
    unittest.main()
