"""Contrôles ciblés des configurations fixées avant les scores."""

import unittest
import math

from fraud_investigation.ml_benchmark import candidate
from fraud_investigation.ml_feature_ratio_recipient_history import RatioRecipientFeatures
from fraud_investigation.ml_tune_h import CONFIGS, configured_model


class TuneHTest(unittest.TestCase):
    def test_exact_configs_and_single_changes(self):
        self.assertEqual(len(CONFIGS), 6)
        for code, (name, changes) in CONFIGS.items():
            reference = candidate(name).get_params()
            tuned = configured_model(code).get_params()
            self.assertEqual({k: tuned[k] for k in changes}, changes)
            for key in reference:
                if key not in changes:
                    if isinstance(reference[key], float) and math.isnan(reference[key]):
                        self.assertTrue(math.isnan(tuned[key]))
                    else:
                        self.assertEqual(reference[key], tuned[key])
            self.assertEqual(tuned.get("random_state", tuned.get("random_seed")), 42)

    def test_exact_h_predictors(self):
        for name in ("xgboost", "catboost"):
            columns = RatioRecipientFeatures(name).columns
            self.assertEqual(columns[-2:], ["part_solde", "nb_entrees_anterieures"])
            self.assertEqual(len(columns), 11 if name == "xgboost" else 7)
            self.assertFalse(set(columns) & {"step", "nameDest", "isFraud", "newbalanceOrig"})


if __name__ == "__main__":
    unittest.main()
