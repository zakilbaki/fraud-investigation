"""Vérifier la règle de départage annoncée pour les réglages de H."""

import unittest

from scripts.report_ml_tune_h_selection import select


def row(code, mean, minimum, std=.03, seconds=3, size=100):
    return {"config": code, "f1_mean": mean, "f1_min": minimum, "f1_std": std,
            "fit_seconds_median": seconds, "serialized_bytes_median": size}


class SelectionTest(unittest.TestCase):
    def test_close_mean_uses_minimum(self):
        chosen, steps = select([row("xgb_depth4", .900, .870), row("cat_depth4", .902, .860)])
        self.assertEqual(chosen, "xgb_depth4")
        self.assertEqual(len(steps[0]["candidates"]), 2)

    def test_far_mean_excludes_candidate(self):
        chosen, steps = select([row("xgb_depth4", .900, .870), row("cat_depth4", .906, .880)])
        self.assertEqual(chosen, "cat_depth4")
        self.assertEqual(steps[0]["candidates"], ["cat_depth4"])

    def test_near_minimum_uses_dispersion(self):
        chosen, _ = select([row("xgb_depth4", .900, .870, .030),
                            row("cat_depth4", .901, .868, .020)])
        self.assertEqual(chosen, "cat_depth4")


if __name__ == "__main__":
    unittest.main()
