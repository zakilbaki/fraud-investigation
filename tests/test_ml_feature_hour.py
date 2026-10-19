"""Contrats ciblés de l'expérience A, sans relire PaySim."""

import unittest

import numpy as np

from fraud_investigation.ml_benchmark import FOLDS, TYPES
from fraud_investigation.ml_feature_hour import HourFeatures, cyclic_hour


class HourExperimentTests(unittest.TestCase):
    def test_hour_cycles_and_origin(self):
        steps = np.array([1, 7, 13, 19, 24, 25, 504], dtype=np.int16)
        result = cyclic_hour(steps)
        np.testing.assert_allclose(result[0], [0, 1], atol=1e-6)
        np.testing.assert_allclose(result[1], [1, 0], atol=1e-6)
        np.testing.assert_allclose(result[2], [0, -1], atol=1e-6)
        np.testing.assert_allclose(result[0], result[5], atol=1e-6)
        self.assertEqual(result.shape, (7, 2))

    def test_transmitted_columns_and_train_only_scaling(self):
        kind = np.array([0, 1, 4, 3], dtype=np.uint8)
        amount = np.array([0, 10, 100, 1_000], dtype=np.float32)
        step = np.array([1, 2, 25, 26], dtype=np.int16)
        forbidden = {"isFraud", "isFlaggedFraud", "oldbalanceOrg", "oldbalanceDest",
                     "newbalanceOrig", "newbalanceDest", "step", "nameOrig", "nameDest"}
        for name in ("xgboost", "catboost", "extra_trees", "random_forest", "knn"):
            features = HourFeatures(name).fit(kind[:2], amount[:2])
            x = features.transform(kind, amount, step)
            self.assertFalse(forbidden.intersection(features.columns))
            self.assertEqual(list(x.columns) if name == "catboost" else x.shape[1],
                             features.columns if name == "catboost" else len(features.columns))
            if name != "catboost":
                np.testing.assert_allclose(x[:, -2:], cyclic_hour(step), atol=1e-6)
                np.testing.assert_array_equal(x[:, :len(TYPES)], np.eye(len(TYPES))[kind])
            if name == "knn":
                self.assertAlmostEqual(float(features.reference.scaler.mean_[0]),
                                       float(np.log1p(amount[:2]).mean()), places=5)

    def test_chronological_portions(self):
        for fit_end, reserve_end, validation_end in FOLDS:
            self.assertEqual(reserve_end - fit_end, 72)
            self.assertEqual(validation_end - reserve_end, 72)
            self.assertLess(validation_end, 505)


if __name__ == "__main__":
    unittest.main()
