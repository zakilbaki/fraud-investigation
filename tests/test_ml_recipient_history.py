"""Contrats synthétiques du compteur G, sans charger PaySim."""

import unittest

import polars as pl

from fraud_investigation.ml_recipient_history import (
    recipient_step_coverage, recipient_step_history,
)


class RecipientHistoryTests(unittest.TestCase):
    def test_prior_only_same_step_duplicates_future_and_order(self):
        rows = [(3, "A"), (1, "A"), (2, "B"), (2, "A"),
                (2, "A"), (4, "A"), (1, "C"), (3, "B")]
        frame = pl.DataFrame(rows, schema=["step", "nameDest"], orient="row")
        expected = {("A", 1): (1, 0), ("A", 2): (2, 1),
                    ("A", 3): (1, 3), ("A", 4): (1, 4),
                    ("B", 2): (1, 0), ("B", 3): (1, 1),
                    ("C", 1): (1, 0)}
        for candidate in (frame, frame.reverse()):
            grouped = recipient_step_history(candidate)
            self.assertEqual({(r["nameDest"], r["step"]):
                              (r["transactions"], r["prior_count"])
                              for r in grouped.iter_rows(named=True)}, expected)
            coverage = recipient_step_coverage(grouped)
            self.assertEqual(coverage["rows"].sum(), len(rows))
            self.assertEqual(coverage["nonzero_rows"].sum(), 5)

    def test_sender_role_or_label_rejected(self):
        with self.assertRaises(ValueError):
            recipient_step_history(pl.DataFrame({"step": [1], "nameOrig": ["A"]}))
        with self.assertRaises(ValueError):
            recipient_step_history(pl.DataFrame({"step": [1], "nameDest": ["A"],
                                                 "isFraud": [1]}))


if __name__ == "__main__":
    unittest.main()
