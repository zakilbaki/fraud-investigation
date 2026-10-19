"""Cas synthétiques pour le compteur F, sans PaySim ni labels."""

import unittest

import polars as pl

from fraud_investigation.ml_sender_history import sender_step_history, step_coverage


class SenderHistoryTests(unittest.TestCase):
    def test_strict_prior_duplicate_same_step_future_and_row_order(self):
        rows = [(3, "A"), (1, "A"), (2, "B"), (2, "A"),
                (2, "A"), (4, "A"), (1, "C"), (3, "B")]
        frame = pl.DataFrame(rows, schema=["step", "nameOrig"], orient="row")
        expected = {("A", 1): (1, 0), ("A", 2): (2, 1),
                    ("A", 3): (1, 3), ("A", 4): (1, 4),
                    ("B", 2): (1, 0), ("B", 3): (1, 1),
                    ("C", 1): (1, 0)}
        for candidate in (frame, frame.reverse()):
            grouped = sender_step_history(candidate)
            actual = {(r["nameOrig"], r["step"]):
                      (r["transactions"], r["prior_count"])
                      for r in grouped.iter_rows(named=True)}
            self.assertEqual(actual, expected)
            coverage = step_coverage(grouped)
            self.assertEqual(coverage["rows"].sum(), len(rows))
            self.assertEqual(coverage["nonzero_rows"].sum(), 5)

    def test_rejects_other_roles_or_labels(self):
        with self.assertRaises(ValueError):
            sender_step_history(pl.DataFrame({"step": [1], "nameDest": ["A"]}))
        with self.assertRaises(ValueError):
            sender_step_history(pl.DataFrame({"step": [1], "nameOrig": ["A"],
                                              "isFraud": [1]}))


if __name__ == "__main__":
    unittest.main()
