"""Contrats synthétiques du compteur G, sans charger PaySim."""

import unittest

import polars as pl

from fraud_investigation.ml_recipient_history import (
    counts_for_rows, recipient_step_coverage, recipient_step_history,
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

    def test_join_restores_row_order_and_ignores_labels(self):
        frame = pl.DataFrame({"step": [3, 1, 2, 2, 4],
                              "nameDest": ["A", "A", "A", "A", "A"],
                              "isFraud": [1, 0, 0, 1, 1]})
        self.assertEqual(counts_for_rows(frame).to_list(), [3, 0, 1, 1, 4])
        flipped = frame.with_columns((1-pl.col("isFraud")).alias("isFraud"))
        self.assertEqual(counts_for_rows(flipped).to_list(), [3, 0, 1, 1, 4])


if __name__ == "__main__":
    unittest.main()
