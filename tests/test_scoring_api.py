import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
from fastapi.testclient import TestClient

from fraud_investigation.api import create_app
from fraud_investigation.database import APP_SCHEMA, SEARCH_INDEXES, count_prior_receipts, open_readonly
from fraud_investigation.ml_feature_ratio_recipient_history import RatioRecipientFeatures
from fraud_investigation.ml_final import MODEL_COLUMNS, sha256
from fraud_investigation.scoring_service import FINAL_THRESHOLD, ScoreService, ScoringPaths


class FixedModel:
    def __init__(self, value):
        self.value = value
        self.last_features = None

    def get_params(self):
        return {}

    def predict_proba(self, x):
        self.last_features = x.copy()
        return np.array([[1 - self.value, self.value] for _ in range(len(x))])


class ScoringApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.database, self.model, self.manifest = (root / name for name in
                                                     ("app.sqlite", "pipeline.joblib", "manifest.json"))
        source = bytes.fromhex("00" * 32)
        with sqlite3.connect(self.database) as connection:
            connection.executescript(APP_SCHEMA)
            connection.executemany("INSERT INTO accounts(account_id) VALUES (?)",
                                   [("O1",), ("O2",), ("O3",), ("D1",), ("D2",)])
            transactions = (
                (2, 1, "TRANSFER", "10", "5", "O1", "D1"),
                (3, 2, "CASH_OUT", "0", "0", "O2", "D1"),
                (4, 2, "CASH_OUT", "20", "10", "O3", "D1"),
                (5, 3, "TRANSFER", "30", "15", "O1", "D1"),
                (6, 3, "PAYMENT", "5", "5", "O2", "D2"),
            )
            for line, step, kind, amount, balance, origin, dest in transactions:
                connection.execute("""INSERT INTO transactions VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (line, line.to_bytes(16, "big"), source, step, kind, amount,
                     origin, balance, balance, dest, "0", "0"))
            connection.executescript(SEARCH_INDEXES)
        features = RatioRecipientFeatures("catboost").fit(
            np.array([1], dtype=np.uint8), np.array([1], dtype=np.float32),
            np.array([1], dtype=np.float32), np.array([0], dtype=np.float32))
        joblib.dump({"features": features, "model": FixedModel(FINAL_THRESHOLD),
                     "threshold": FINAL_THRESHOLD}, self.model)
        self.manifest.write_text(json.dumps({
            "csv_sha256": "00" * 32, "pipeline_sha256": sha256(self.model),
            "model_config": "cat_slow200", "threshold": FINAL_THRESHOLD,
            "predictor_columns": list(MODEL_COLUMNS), "model_parameters": {},
        }))
        self.paths = ScoringPaths(self.database, self.model, self.manifest)

    def tearDown(self):
        self.directory.cleanup()

    def test_readonly_count_excludes_same_step_and_has_no_limit(self):
        with open_readonly(self.database) as connection:
            self.assertEqual(count_prior_receipts(connection, "D1", 1), 0)
            self.assertEqual(count_prior_receipts(connection, "D1", 2), 1)
            self.assertEqual(count_prior_receipts(connection, "D1", 3), 3)

    def test_count_is_not_capped_at_500(self):
        source = bytes.fromhex("00" * 32)
        with sqlite3.connect(self.database) as connection:
            connection.executemany("""INSERT INTO transactions VALUES
                (?, ?, ?, 1, 'PAYMENT', '1', 'O1', '1', '1', 'D1', '0', '0')""",
                [(line, line.to_bytes(16, "big"), source) for line in range(10, 511)])
        with open_readonly(self.database) as connection:
            self.assertEqual(count_prior_receipts(connection, "D1", 2), 502)

    def test_score_features_and_exact_threshold(self):
        service = ScoreService(self.paths)
        service.load()
        zero = service.score_transaction((3).to_bytes(16, "big").hex())
        self.assertEqual(zero["suspicion_score"], FINAL_THRESHOLD)
        self.assertTrue(zero["alert"])
        x = service.model.last_features
        self.assertTrue(np.isnan(x["part_solde"].iloc[0]))
        self.assertEqual(x["nb_entrees_anterieures"].iloc[0], 1)
        self.assertEqual(x["amount"].iloc[0], 0)
        service.score_transaction((4).to_bytes(16, "big").hex())
        self.assertEqual(service.model.last_features["nb_entrees_anterieures"].iloc[0], 1)
        service.score_transaction((5).to_bytes(16, "big").hex())
        self.assertEqual(service.model.last_features["nb_entrees_anterieures"].iloc[0], 3)

    def test_endpoints_reload_and_errors(self):
        for _ in range(2):
            with TestClient(create_app(self.paths)) as client:
                self.assertEqual(client.get("/health").json()["status"], "ready")
                response = client.post("/score", json={"transaction_id": (3).to_bytes(16, "big").hex()})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["alert"])
                self.assertEqual(response.json()["policy_version"], "final_global_f1_v1")
                self.assertEqual(client.post("/score", json={"transaction_id": "bad"}).status_code, 400)
                self.assertEqual(client.post("/score", json={"transaction_id": "ff" * 16}).status_code, 404)
                self.assertEqual(client.post("/score", json={"transaction_id": 123}).status_code, 422)
        with TestClient(create_app(ScoringPaths(self.database, self.model.with_name("missing.joblib"),
                                                self.manifest))) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 503)
            self.assertEqual(health.json()["detail"], "Modèle local absent")
            self.assertEqual(client.post("/score", json={"transaction_id": "00" * 16}).status_code, 503)

    def test_incompatible_artifact(self):
        manifest = json.loads(self.manifest.read_text())
        manifest["pipeline_sha256"] = "ff" * 32
        self.manifest.write_text(json.dumps(manifest))
        with TestClient(create_app(self.paths)) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 503)
            self.assertIn("incompatible", health.json()["detail"])
            self.assertEqual(client.post("/score", json={"transaction_id": "00" * 16}).status_code, 503)

    def test_incompatible_transaction_data(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE transactions SET amount='invalid' WHERE source_line_number=3")
        with TestClient(create_app(self.paths)) as client:
            response = client.post("/score", json={"transaction_id": (3).to_bytes(16, "big").hex()})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("Traceback", response.text)


if __name__ == "__main__":
    unittest.main()
