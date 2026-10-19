"""Contrats ciblés de H sans charger PaySim."""

import unittest

import numpy as np
import polars as pl

from fraud_investigation.ml_feature_balance_share import ShareFeatures, balance_share
from fraud_investigation.ml_feature_ratio_recipient_history import (
    MODELS, SOURCE_COLUMNS, RatioRecipientFeatures,
)
from fraud_investigation.ml_recipient_history import counts_for_rows


class RatioRecipientHistoryTests(unittest.TestCase):
    def test_exact_e_prefix_g_suffix_and_missing_ratio(self):
        self.assertEqual(SOURCE_COLUMNS,
                         ("step", "type", "amount", "oldbalanceOrg", "nameDest", "isFraud"))
        kind = np.array([0, 1, 4, 3], dtype=np.uint8)
        amount = np.array([10, 3, 0, 20], dtype=np.float32)
        balance = np.array([20, 0, 0, 5], dtype=np.float32)
        step = np.array([1, 2, 24, 25], dtype=np.int16)
        prior = np.array([0, 1, 2, 112], dtype=np.float32)
        forbidden = {"nameDest", "nameOrig", "step", "isFraud", "isFlaggedFraud",
                     "oldbalanceDest", "newbalanceOrig", "newbalanceDest",
                     "nb_sorties_anterieures"}
        for name in MODELS:
            h = RatioRecipientFeatures(name).fit(kind[:2], amount[:2], balance[:2], prior[:2])
            e = ShareFeatures(name).fit(kind[:2], amount[:2], balance[:2])
            self.assertEqual(h.columns, [*e.columns, "nb_entrees_anterieures"])
            self.assertFalse(forbidden.intersection(h.columns))
            x = h.transform(kind, amount, balance, step, prior)
            e_x = e.transform(kind, amount, balance, step)
            if name == "catboost":
                np.testing.assert_array_equal(x[e.columns].to_numpy(), e_x.to_numpy())
                ratio = x["part_solde"].to_numpy()
                history = x["nb_entrees_anterieures"].to_numpy()
            else:
                np.testing.assert_array_equal(x[:, :-1], e_x)
                ratio, history = x[:, -2], x[:, -1]
            np.testing.assert_equal(ratio, balance_share(amount, balance))
            np.testing.assert_array_equal(history, prior)
            self.assertTrue(np.isnan(ratio[1]))
            self.assertTrue(np.isnan(ratio[2]))
            self.assertEqual(ratio[3], 4.0)

    def test_history_stays_strictly_prior_in_combination(self):
        frame = pl.DataFrame({"step": [3, 1, 2, 2, 4],
                              "nameDest": ["A", "A", "A", "A", "A"],
                              "isFraud": [1, 0, 0, 1, 1]})
        self.assertEqual(counts_for_rows(frame).to_list(), [3, 0, 1, 1, 4])
        self.assertEqual(counts_for_rows(frame.reverse()).to_list(), [4, 1, 1, 0, 3])
        changed = frame.with_columns((1 - pl.col("isFraud")).alias("isFraud"))
        self.assertEqual(counts_for_rows(changed).to_list(), [3, 0, 1, 1, 4])


if __name__ == "__main__":
    unittest.main()
