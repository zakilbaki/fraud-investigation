import unittest

import numpy as np

from fraud_investigation.ml_benchmark import choose_threshold, metrics


class BenchmarkRulesTest(unittest.TestCase):
    def test_tied_scores_stay_grouped(self):
        labels = np.array([1, 0, 1, 0], dtype=np.uint8)
        scores = np.array([0.8, 0.8, 0.2, 0.2])
        threshold, f1 = choose_threshold(labels, scores)
        self.assertEqual(threshold, 0.2)
        self.assertAlmostEqual(f1, 2 / 3)
        self.assertEqual(metrics(labels, scores, threshold)["alerts"], 4)

    def test_highest_threshold_breaks_equal_f1(self):
        labels = np.array([1, 0, 0, 1], dtype=np.uint8)
        scores = np.array([0.9, 0.8, 0.7, 0.6])
        threshold, f1 = choose_threshold(labels, scores)
        self.assertEqual(threshold, 0.9)
        self.assertAlmostEqual(f1, 2 / 3)

    def test_no_alert_convention(self):
        result = metrics(np.array([0, 1]), np.array([0.1, 0.2]), 0.3)
        self.assertEqual((result["precision"], result["recall"], result["f1"]), (0, 0, 0))
        self.assertEqual((result["fp"], result["fn"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
