import unittest

import numpy as np

from fraud_investigation.ml_cashout_threshold import decision_metrics, selected_threshold
from fraud_investigation.ml_benchmark import metrics


class CashoutThresholdTests(unittest.TestCase):
    def test_lower_candidate_improves_f1_and_identical_scores_stay_grouped(self):
        label = np.array([1, 1, 0, 0], dtype=np.uint8)
        score = np.array([0.8, 0.2, 0.2, 0.1])
        self.assertEqual(selected_threshold(label, score, 0.5), 0.2)

    def test_no_improvement_keeps_global_threshold(self):
        label = np.array([1, 0, 0], dtype=np.uint8)
        score = np.array([0.8, 0.2, 0.1])
        self.assertEqual(selected_threshold(label, score, 0.5), 0.5)

    def test_equal_f1_uses_highest_threshold(self):
        label = np.array([1, 0, 0, 1], dtype=np.uint8)
        score = np.array([0.8, 0.6, 0.4, 0.2])
        self.assertEqual(selected_threshold(label, score, 0.7), 0.7)

    def test_decision_metrics_agree_with_single_threshold(self):
        label = np.array([1, 0, 1, 0], dtype=np.uint8)
        score = np.array([0.9, 0.8, 0.2, 0.1])
        self.assertEqual(decision_metrics(label, score >= 0.5), metrics(label, score, 0.5))


if __name__ == "__main__":
    unittest.main()
