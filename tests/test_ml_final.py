"""Frontières temporelles et diagnostics du gel final sur données synthétiques."""

import unittest
import tempfile
from pathlib import Path

import json

import numpy as np

from fraud_investigation.ml_final import MODEL_COLUMNS, verify_or_publish_manifest
from fraud_investigation.ml_final_test import amount_bucket, stepwise_history, subgroup


class FinalTest(unittest.TestCase):
    def test_history_boundary_same_step_and_future(self):
        names = np.array(["A", "A", "B", "A", "B", "A"], dtype=object)
        steps = np.array([505, 505, 505, 506, 506, 507])
        initial = {"A": 3, "B": 1}
        result = np.empty(len(names), dtype=np.float32)
        for _, indices, prior in stepwise_history(names, steps, initial):
            result[indices] = prior
        np.testing.assert_array_equal(result, [3, 3, 1, 5, 2, 6])
        # Une permutation de lignes du même step ne change pas les comptes.
        order = np.array([2, 0, 1, 4, 3, 5])
        permuted = np.empty(len(names), dtype=np.float32)
        for _, indices, prior in stepwise_history(names[order], steps[order], initial):
            permuted[indices] = prior
        np.testing.assert_array_equal(permuted[np.argsort(order)], result)

    def test_future_steps_never_feed_prior(self):
        rows = [(s, idx, p.tolist()) for s, idx, p in
                stepwise_history(["A", "A"], [505, 507], {})]
        self.assertEqual(rows[0][2], [0])
        self.assertEqual(rows[1][2], [1])
        with self.assertRaises(ValueError):
            list(stepwise_history(["A"], [504], {}))

    def test_unseen_recipient_at_test_boundary_starts_at_zero(self):
        initial = {"KNOWN": 2}
        names = np.array(["NEW", "KNOWN", "NEW"], dtype=object)
        steps = np.array([505, 505, 506])
        result = np.empty(len(names), dtype=np.float32)
        for current_step, indices, prior in stepwise_history(names, steps, initial):
            if current_step == 505:
                expected = np.fromiter((initial.get(name, 0) for name in names[indices]),
                                       dtype=np.float32, count=len(indices))
                np.testing.assert_array_equal(prior, expected)
            result[indices] = prior
        np.testing.assert_array_equal(result, [0, 2, 1])

    def test_bucket_boundaries_and_absent_group(self):
        values = np.array([0, 1, 99999.99, 100000, 10**5.5, 1e6, 10**6.5, 1e8])
        np.testing.assert_array_equal(amount_bucket(values), [0, 1, 1, 2, 3, 4, 5, 5])
        empty = subgroup(np.array([1]), np.array([.7]), .5, np.array([False]))
        self.assertIsNone(empty["precision"])
        self.assertIsNone(empty["f1"])

    def test_predictor_contract(self):
        self.assertEqual(MODEL_COLUMNS, ("type", "amount", "oldbalanceOrg", "hour_sin",
                                         "hour_cos", "part_solde", "nb_entrees_anterieures"))
        self.assertNotIn("isFraud", MODEL_COLUMNS)
        self.assertNotIn("nameDest", MODEL_COLUMNS)

    def test_reconstruction_preserves_published_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            verify_or_publish_manifest({"hash": "expected"}, path)
            original = path.read_bytes()
            verify_or_publish_manifest({"hash": "expected"}, path)
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(AssertionError):
                verify_or_publish_manifest({"hash": "different"}, path)
            self.assertEqual(json.loads(path.read_text()), {"hash": "expected"})


if __name__ == "__main__":
    unittest.main()
