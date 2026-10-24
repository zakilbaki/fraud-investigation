import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from fraud_investigation.api import create_app
from fraud_investigation.database import APP_SCHEMA, SEARCH_INDEXES
from fraud_investigation.evidence_service import execute_and_record
from fraud_investigation.scoring_service import FINAL_THRESHOLD, ScoringPaths


class SimulatedScorer:
    """Réponse synthétique pour vérifier la mise en forme, pas le modèle final."""

    def score_transaction(self, transaction_id):
        return {"transaction_id": transaction_id, "suspicion_score": FINAL_THRESHOLD,
                "threshold": FINAL_THRESHOLD, "alert": True,
                "model_version": "simulated_test_model", "policy_version": "simulated_test_policy"}


class ReportApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "app.sqlite"
        self.transaction_id = (3).to_bytes(16, "big").hex()
        with sqlite3.connect(self.database) as connection:
            connection.executescript(APP_SCHEMA)
            connection.executemany("INSERT INTO accounts VALUES (?)", [("A",), ("B",)])
            for line, step in ((2, 1), (3, 2)):
                connection.execute(
                    "INSERT INTO transactions VALUES (?, ?, ?, ?, 'TRANSFER', '10.00', "
                    "'A', '20.00', '10.00', 'B', '0.00', '10.00')",
                    (line, line.to_bytes(16, "big"), b"\x00" * 32, step),
                )
            connection.executescript(SEARCH_INDEXES)
        self.paths = ScoringPaths(self.database, self.database.with_name("missing.joblib"),
                                  self.database.with_name("missing.json"))

    def tearDown(self):
        self.directory.cleanup()

    def test_partial_report_errors_comments_and_immutable_versions(self):
        with TestClient(create_app(self.paths)) as client:
            case_id = client.post("/cases", headers={"Idempotency-Key": "case"},
                                  json={"transaction_id": self.transaction_id}).json()["case_id"]
            self.assertEqual(client.get(f"/cases/{case_id}/reports").json()["reports"], [])
            self.assertEqual(client.get(f"/cases/{case_id}/runs").json()["runs"], [])
            comment = client.post(f"/cases/{case_id}/events",
                                  headers={"Idempotency-Key": "comment"},
                                  json={"event_type": "comment", "origin": "agent",
                                        "content": {"text": "Je soupçonne une fraude"}}).json()
            claimed = client.post(f"/cases/{case_id}/events",
                                  headers={"Idempotency-Key": "claim"},
                                  json={"event_type": "tool_result", "origin": "tool",
                                        "content": {"claim": "fraude prouvée"}}).json()
            transaction = client.post(f"/cases/{case_id}/runs",
                                      headers={"Idempotency-Key": "tx"},
                                      json={"operation": "transaction"}).json()
            unavailable = client.post(f"/cases/{case_id}/runs",
                                      headers={"Idempotency-Key": "score"},
                                      json={"operation": "score"}).json()
            report1 = client.post(f"/cases/{case_id}/reports").json()
            self.assertEqual(report1["version"], 1)
            body = report1["body"]
            self.assertIsNone(body["score"])
            self.assertEqual(body["provenance"]["evidence_ref"], transaction["run_id"])
            self.assertTrue(all(fact["evidence_ref"] == transaction["run_id"]
                                for fact in body["facts"]))
            self.assertNotIn("newbalance_orig", [fact["name"] for fact in body["facts"]])
            self.assertNotIn("isFraud", report1["markdown"])
            self.assertEqual(body["errors"][0]["evidence_ref"], unavailable["run_id"])
            self.assertIn("ML score unavailable or not executed", body["missing"])
            self.assertEqual(body["comments"][0]["event_id"], comment["event_id"])
            self.assertEqual(body["caller_submitted_results"][0]["event_id"], claimed["event_id"])
            self.assertNotIn("fraude prouvée", str(body["facts"]))
            self.assertIn("Caller declarations, unverified", report1["markdown"])
            self.assertEqual(client.get(f"/cases/{case_id}/reports/1/markdown").status_code, 200)
            self.assertEqual(client.get(f"/cases/{case_id}/reports/1/markdown").text,
                             report1["markdown"])

            history = client.post(f"/cases/{case_id}/runs",
                                  headers={"Idempotency-Key": "history"},
                                  json={"operation": "sender_history", "limit": 1}).json()
            report2 = client.post(f"/cases/{case_id}/reports").json()
            self.assertEqual(report2["version"], 2)
            self.assertEqual(report2["body"]["histories"][0]["evidence_ref"], history["run_id"])
            self.assertEqual(client.get(f"/cases/{case_id}/reports/1").json(), report1)
            listing = client.get(f"/cases/{case_id}/reports?limit=1").json()
            self.assertTrue(listing["truncated"])
            self.assertEqual(listing["reports"][0]["version"], 2)

        with TestClient(create_app(self.paths)) as client:
            self.assertEqual(client.get(f"/cases/{case_id}/reports/1").json(), report1)

        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM investigation_reports").fetchone()[0], 2)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_successful_score_report_uses_recorded_stub_score(self):
        with TestClient(create_app(self.paths)) as client:
            case_id = client.post("/cases", headers={"Idempotency-Key": "case"},
                                  json={"transaction_id": self.transaction_id}).json()["case_id"]
            score_run = execute_and_record(self.database, case_id, "stub-score", "score", {},
                                           scorer=SimulatedScorer())
            report = client.post(f"/cases/{case_id}/reports").json()
            score = report["body"]["score"]
            self.assertEqual(score["evidence_ref"], score_run["run_id"])
            self.assertEqual(score["threshold"], FINAL_THRESHOLD)
            self.assertEqual(score["model_version"], "simulated_test_model")
            self.assertIn("not confirmed fraud", score["interpretation"])
            self.assertIn("not a calibrated", str(report["body"]["limits"]))
            self.assertIn("simulated_test_model", report["markdown"])
            self.assertIn("transaction facts unavailable or not executed",
                          report["body"]["missing"])

    def test_incomplete_run_is_not_presented_as_a_fact(self):
        with TestClient(create_app(self.paths)) as client:
            case_id = client.post("/cases", headers={"Idempotency-Key": "case"},
                                  json={"transaction_id": self.transaction_id}).json()["case_id"]

            def stop_after_claim():
                raise RuntimeError("synthetic interruption")

            with self.assertRaises(RuntimeError):
                execute_and_record(self.database, case_id, "pending", "transaction", {},
                                   after_claim=stop_after_claim)
            report = client.post(f"/cases/{case_id}/reports").json()
            self.assertEqual(report["body"]["facts"], [])
            self.assertIsNone(report["body"]["provenance"])
            self.assertEqual(len(report["body"]["incomplete"]), 1)
            self.assertIn("run in progress or interrupted", report["markdown"])


if __name__ == "__main__":
    unittest.main()
