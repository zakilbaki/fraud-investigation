"""Contrats ciblés de D sans charger PaySim."""

import unittest

import numpy as np

from fraud_investigation.ml_benchmark import FOLDS
from fraud_investigation.ml_feature_balance_org import BalanceFeatures, MODELS, SOURCE_COLUMNS
from fraud_investigation.ml_feature_balance_org_hour import CombinedFeatures
from fraud_investigation.ml_feature_hour import cyclic_hour


class BalanceOrgHourTests(unittest.TestCase):
    def test_source_projection_and_windows(self):
        self.assertEqual(SOURCE_COLUMNS, ("step", "type", "amount", "oldbalanceOrg", "isFraud"))
        self.assertEqual(MODELS, ("xgboost", "catboost", "extra_trees", "random_forest"))
        for fit_end, reserve_end, val_end in FOLDS:
            self.assertEqual(reserve_end - fit_end, 72)
            self.assertEqual(val_end - reserve_end, 72)
            self.assertLess(val_end, 505)

    def test_b_prefix_and_a_hour_are_exact(self):
        kind = np.array([0, 1, 4, 3], dtype=np.uint8)
        amount = np.array([0, 10, 100, 1000], dtype=np.float32)
        balance = np.array([0, 20, 200, 2000], dtype=np.float32)
        step = np.array([1, 7, 24, 25], dtype=np.int16)
        forbidden = {"oldbalanceDest", "newbalanceOrig", "newbalanceDest", "isFraud",
                     "isFlaggedFraud", "step", "nameOrig", "nameDest"}
        for name in MODELS:
            d = CombinedFeatures(name).fit(kind[:2], amount[:2], balance[:2])
            b = BalanceFeatures(name).fit(kind[:2], amount[:2], balance[:2])
            x = d.transform(kind, amount, balance, step)
            b_x = b.transform(kind, amount, balance)
            self.assertEqual(d.columns, [*b.columns, "hour_sin", "hour_cos"])
            self.assertFalse(forbidden.intersection(d.columns))
            if name == "catboost":
                self.assertEqual(list(x.columns), d.columns)
                np.testing.assert_array_equal(x[b.columns].to_numpy(), b_x.to_numpy())
                np.testing.assert_allclose(x[["hour_sin", "hour_cos"]].to_numpy(),
                                           cyclic_hour(step), atol=1e-6)
            else:
                np.testing.assert_array_equal(x[:, :-2], b_x)
                np.testing.assert_allclose(x[:, -2:], cyclic_hour(step), atol=1e-6)
            self.assertEqual(float(b_x["oldbalanceOrg"][0] if name == "catboost"
                                   else b_x[0, -1]), 0.0)

    def test_invalid_input_rejected(self):
        d = CombinedFeatures("xgboost").fit(np.array([0], dtype=np.uint8),
                                              np.array([1], dtype=np.float32),
                                              np.array([0], dtype=np.float32))
        with self.assertRaises(AssertionError):
            d.transform(np.array([0], dtype=np.uint8), np.array([1], dtype=np.float32),
                        np.array([-1], dtype=np.float32), np.array([1], dtype=np.int16))
        with self.assertRaises(AssertionError):
            d.transform(np.array([0], dtype=np.uint8), np.array([1], dtype=np.float32),
                        np.array([0], dtype=np.float32), np.array([0], dtype=np.int16))


if __name__ == "__main__":
    unittest.main()
