"""Protected scoring contracts using an explicitly synthetic fixed-score model."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
from fastapi.testclient import TestClient

from fraud_investigation.copilot_api import create_copilot_app
from fraud_investigation.database import APP_SCHEMA, SEARCH_INDEXES
from fraud_investigation.ml_feature_ratio_recipient_history import RatioRecipientFeatures
from fraud_investigation.ml_final import MODEL_COLUMNS, sha256
from fraud_investigation.scoring_service import FINAL_THRESHOLD, POLICY_VERSION
from scripts.export_copilot_openapi import SCORING_TEMPLATE, export


class SyntheticThresholdModel:
    """Return the threshold to check decision equality, not predictive quality."""

    def get_params(self):
        return {}

    def predict_proba(self, x):
        self.last_features = x.copy()
        return np.array([[1 - FINAL_THRESHOLD, FINAL_THRESHOLD] for _ in range(len(x))])


class CopilotScoringTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.database, self.model, self.manifest = [root / name for name in
                                                   ("app.sqlite", "model.joblib", "manifest.json")]
        self.key = "synthetic-test-key-of-at-least-32-characters"
        self.headers = {"X-API-Key": self.key}
        self.transaction_id = (3).to_bytes(16, "big").hex()
        with sqlite3.connect(self.database) as db:
            db.executescript(APP_SCHEMA)
            db.executemany("INSERT INTO accounts VALUES (?)", [("A",), ("B",)])
            for line, step in [(2, 1), (3, 2), (4, 2), (5, 3)]:
                db.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, 'CASH_OUT', "
                           "'10', 'A', '0', '0', 'B', '0', '0')",
                           (line, line.to_bytes(16, "big"), b"\x00" * 32, step))
            db.executescript(SEARCH_INDEXES)
        features = RatioRecipientFeatures("catboost").fit(
            np.array([1], dtype=np.uint8), np.array([1], dtype=np.float32),
            np.array([1], dtype=np.float32), np.array([0], dtype=np.float32))
        joblib.dump({"features": features, "model": SyntheticThresholdModel(),
                     "threshold": FINAL_THRESHOLD}, self.model)
        self.manifest.write_text(json.dumps({
            "csv_sha256": "00" * 32, "pipeline_sha256": sha256(self.model),
            "model_config": "cat_slow200", "threshold": FINAL_THRESHOLD,
            "predictor_columns": list(MODEL_COLUMNS), "model_parameters": {},
        }))

    def tearDown(self):
        self.directory.cleanup()

    def app(self):
        return create_copilot_app(self.database, api_key=self.key,
                                  model_path=self.model, manifest_path=self.manifest)

    def test_scoring_requires_key_and_does_not_leak_it(self):
        with TestClient(self.app()) as client:
            for headers in ({}, {"X-API-Key": "wrong"}):
                response = client.post("/score", headers=headers,
                                       json={"transaction_id": self.transaction_id})
                self.assertEqual(response.status_code, 401)
                self.assertNotIn(self.key, response.text)

    def test_frozen_pipeline_response_and_strict_history(self):
        app = self.app()
        with TestClient(app) as client:
            result = client.post("/score", headers=self.headers,
                                 json={"transaction_id": self.transaction_id})
            self.assertEqual(result.status_code, 200)
            body = result.json()
            self.assertEqual(set(body), {"transaction_id", "suspicion_score", "threshold",
                                         "alert", "model_version", "policy_version"})
            self.assertEqual(body["threshold"], FINAL_THRESHOLD)
            self.assertEqual(body["suspicion_score"], FINAL_THRESHOLD)
            self.assertTrue(body["alert"])
            self.assertEqual(body["policy_version"], POLICY_VERSION)
            self.assertTrue(body["model_version"].startswith("cat_slow200:"))
            x = app.state.score_service.model.last_features
            self.assertEqual(list(x.columns), list(MODEL_COLUMNS))
            self.assertEqual(x["nb_entrees_anterieures"].iloc[0], 1)
            self.assertTrue(np.isnan(x["part_solde"].iloc[0]))
            self.assertEqual(client.get(f"/transactions/{self.transaction_id}",
                                        headers=self.headers).status_code, 200)
            self.assertEqual(set(app.openapi()["paths"]),
                             {"/transactions/{transaction_id}", "/score",
                              "/transactions/{transaction_id}/sender-history",
                              "/transactions/{transaction_id}/recipient-history",
                              "/accounts/{account_id}/transactions"})
        self.assertEqual(sha256(self.model), json.loads(self.manifest.read_text())["pipeline_sha256"])

    def test_invalid_missing_and_extra_inputs(self):
        with TestClient(self.app()) as client:
            for identifier in ("0", "bad", "g" * 32):
                self.assertEqual(client.post("/score", headers=self.headers,
                                              json={"transaction_id": identifier}).status_code, 400)
            missing = client.post("/score", headers=self.headers,
                                  json={"transaction_id": "f" * 32})
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json()["detail"], "Transaction not found")
            for request in ({}, {"transaction_id": 123},
                            {"transaction_id": self.transaction_id, "threshold": 0}):
                self.assertEqual(client.post("/score", headers=self.headers,
                                              json=request).status_code, 422)

    def test_missing_or_incompatible_model_preserves_lookup(self):
        for incompatible in (True, False):
            if incompatible:
                manifest = json.loads(self.manifest.read_text())
                manifest["pipeline_sha256"] = "f" * 64
                self.manifest.write_text(json.dumps(manifest))
            else:
                self.model.unlink()
            with TestClient(self.app()) as client:
                self.assertEqual(client.get(f"/transactions/{self.transaction_id}",
                                            headers=self.headers).status_code, 200)
                response = client.post("/score", headers=self.headers,
                                       json={"transaction_id": self.transaction_id})
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(str(self.model), response.text)
                self.assertNotIn("suspicion_score", response.json())

    def test_incompatible_data_is_not_scored(self):
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE transactions SET amount='invalid' WHERE source_line_number=3")
        with TestClient(self.app()) as client:
            response = client.post("/score", headers=self.headers,
                                   json={"transaction_id": self.transaction_id})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"],
                             "Transaction data incompatible with the frozen pipeline")

    def test_scoring_export_is_separate_authenticated_and_fully_described(self):
        output = Path(self.directory.name) / "score.swagger.json"
        export("https://tunnel.example.org", output, tool="scoring")
        spec = json.loads(output.read_text())
        self.assertEqual(spec["swagger"], "2.0")
        self.assertEqual(spec["host"], "tunnel.example.org")
        self.assertEqual(list(spec["paths"]), ["/score"])
        self.assertEqual(list(spec["paths"]["/score"]), ["post"])
        operation = spec["paths"]["/score"]["post"]
        self.assertEqual(operation["operationId"], "scoreTransactionById")
        self.assertEqual(operation["security"], [{"ApiKeyAuth": []}])
        self.assertEqual(spec["securityDefinitions"]["ApiKeyAuth"]["name"], "X-API-Key")
        self.assertEqual(operation["parameters"][0]["in"], "body")
        self.assertTrue(all(r["description"] for r in operation["responses"].values()))
        for definition in spec["definitions"].values():
            self.assertTrue(all(p["description"] for p in definition["properties"].values()))
        self.assertEqual(set(spec["definitions"]["Score"]["properties"]),
                         {"transaction_id", "suspicion_score", "threshold", "alert",
                          "model_version", "policy_version"})
        self.assertNotIn(self.key, output.read_text())
        self.assertIn(".invalid", SCORING_TEMPLATE.read_text())
        with self.assertRaises(ValueError):
            export("https://tunnel.example.org", output, tool="unsupported")
