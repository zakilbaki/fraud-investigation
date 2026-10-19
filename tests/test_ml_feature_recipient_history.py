"""Vérifications ciblées du pipeline G sans PaySim."""

import unittest

import numpy as np

from fraud_investigation.ml_feature_balance_org_hour import CombinedFeatures
from fraud_investigation.ml_feature_recipient_history import (
    MODELS, SOURCE_COLUMNS, RecipientFeatures,
)


class RecipientFeatureTests(unittest.TestCase):
    def test_only_raw_recipient_count_added_to_d(self):
        self.assertEqual(SOURCE_COLUMNS,
                         ("step", "type", "amount", "oldbalanceOrg", "nameDest", "isFraud"))
        kind = np.array([0, 1, 4], dtype=np.uint8)
        amount = np.array([0, 10, 100], dtype=np.float32)
        balance = np.array([0, 20, 200], dtype=np.float32)
        step = np.array([1, 2, 25], dtype=np.int16)
        prior = np.array([0, 1, 112], dtype=np.float32)
        forbidden = {"nameDest", "nameOrig", "step", "isFraud", "isFlaggedFraud",
                     "part_solde", "oldbalanceDest", "newbalanceOrig", "newbalanceDest"}
        for name in MODELS:
            g = RecipientFeatures(name).fit(kind[:2], amount[:2], balance[:2], prior[:2])
            d = CombinedFeatures(name).fit(kind[:2], amount[:2], balance[:2])
            self.assertEqual(g.columns, [*d.columns, "nb_entrees_anterieures"])
            self.assertFalse(forbidden.intersection(g.columns))
            x = g.transform(kind, amount, balance, step, prior)
            before = d.transform(kind, amount, balance, step)
            if name == "catboost":
                np.testing.assert_array_equal(x[d.columns].to_numpy(), before.to_numpy())
                np.testing.assert_array_equal(x["nb_entrees_anterieures"].to_numpy(), prior)
            else:
                np.testing.assert_array_equal(x[:, :-1], before)
                np.testing.assert_array_equal(x[:, -1], prior)

    def test_negative_count_rejected(self):
        g = RecipientFeatures("xgboost")
        with self.assertRaises(AssertionError):
            g.fit(np.array([0], dtype=np.uint8), np.array([1], dtype=np.float32),
                  np.array([1], dtype=np.float32), np.array([-1], dtype=np.float32))


if __name__ == "__main__":
    unittest.main()
