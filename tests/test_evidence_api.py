import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from fraud_investigation.api import create_app
from fraud_investigation.database import APP_SCHEMA, SEARCH_INDEXES
from fraud_investigation.evidence_service import execute_and_record
from fraud_investigation.scoring_service import ScoringPaths


class EvidenceApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "app.sqlite"
        self.transaction_id = (5).to_bytes(16, "big").hex()
        with sqlite3.connect(self.database) as connection:
            connection.executescript(APP_SCHEMA)
            connection.executemany("INSERT INTO accounts VALUES (?)", [("A",), ("B",)])
            for line, step, origin, dest in (
                (2, 1, "A", "B"), (3, 2, "B", "A"), (4, 2, "A", "A"),
                (5, 3, "A", "B"),
            ):
                connection.execute(
                    "INSERT INTO transactions VALUES (?, ?, ?, ?, 'TRANSFER', '10.00', "
                    "?, '20.00', '10.00', ?, '0.00', '10.00')",
                    (line, line.to_bytes(16, "big"), b"\x00" * 32, step, origin, dest),
                )
            connection.executescript(SEARCH_INDEXES)
        self.paths = ScoringPaths(self.database, self.database.with_name("missing.joblib"),
                                  self.database.with_name("missing.json"))

    def tearDown(self):
        self.directory.cleanup()

    def test_backend_runs_and_caller_claims_are_distinct(self):
        with TestClient(create_app(self.paths)) as client:
            case = client.post("/cases", headers={"Idempotency-Key": "case"},
                               json={"transaction_id": self.transaction_id}).json()
            case_id = case["case_id"]
            caller = client.post(f"/cases/{case_id}/events",
                                 headers={"Idempotency-Key": "claim"},
                                 json={"event_type": "tool_result", "origin": "tool",
                                       "content": {"verification": "backend_executed",
                                                   "score": 0.99}})
            self.assertEqual(caller.status_code, 201)
            self.assertEqual(caller.json()["verification"], "caller_supplied")
            self.assertEqual(client.post(f"/cases/{case_id}/events",
                                         headers={"Idempotency-Key": "forged"},
                                         json={"event_type": "comment", "origin": "agent",
                                               "content": {}, "verification": "backend_executed"}).status_code, 422)

            def run(operation, key, **kwargs):
                return client.post(f"/cases/{case_id}/runs",
                                   headers={"Idempotency-Key": key},
                                   json={"operation": operation, **kwargs})

            transaction = run("transaction", "tx")
            self.assertEqual(transaction.status_code, 201)
            self.assertEqual(transaction.json()["verification"], "backend_executed")
            self.assertEqual(transaction.json()["result"]["transaction_id"], self.transaction_id)
            self.assertNotIn("newbalance_orig", transaction.json()["result"])
            self.assertNotIn("isFraud", transaction.json()["result"])
            sender = run("sender_history", "sender", limit=2, lookback_steps=2).json()
            self.assertEqual(sender["result"]["before_step"], 3)
            self.assertEqual(sender["result"]["account_id"], "A")
            self.assertTrue(sender["result"]["truncated"])
            self.assertEqual(len(sender["result"]["transactions"]), 2)
            self.assertTrue(all(row["step"] < 3 for row in sender["result"]["transactions"]))
            recipient = run("recipient_history", "recipient", limit=2).json()
            self.assertEqual(recipient["result"]["account_id"], "B")
            self.assertEqual(len(recipient["result"]["transactions"]), 2)
            missing_score = run("score", "score").json()
            self.assertEqual(missing_score["status"], "unavailable")
            self.assertIsNone(missing_score["result"])
            self.assertEqual(missing_score["error"]["code"], "tool_unavailable")
            self.assertEqual(run("score", "score").json(), missing_score)
            self.assertEqual(run("transaction", "tx").json(), transaction.json())
            self.assertEqual(run("recipient_history", "tx").status_code, 409)
            self.assertEqual(run("sql", "bad").status_code, 422)
            self.assertEqual(run("transaction", "bad", database="/tmp/other").status_code, 422)
            self.assertEqual(client.get(f"/cases/{case_id}/runs/{transaction.json()['run_id']}").json(),
                             transaction.json())
            listing = client.get(f"/cases/{case_id}/runs?limit=2").json()
            self.assertTrue(listing["truncated"])
            self.assertEqual(len(listing["runs"]), 2)

        with TestClient(create_app(self.paths)) as client:
            repeated = client.post(f"/cases/{case_id}/runs",
                                   headers={"Idempotency-Key": "tx"},
                                   json={"operation": "transaction"})
            self.assertEqual(repeated.json(), transaction.json())
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM investigation_tool_runs").fetchone()[0], 4)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_incomplete_run_is_visible_without_write_lock(self):
        with TestClient(create_app(self.paths)) as client:
            case_id = client.post("/cases", headers={"Idempotency-Key": "case"},
                                  json={"transaction_id": self.transaction_id}).json()["case_id"]

        def interrupt_after_claim():
            with sqlite3.connect(self.database, timeout=0.1) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.rollback()
            raise RuntimeError("simulated interruption")

        with self.assertRaises(RuntimeError):
            execute_and_record(self.database, case_id, "interrupted", "transaction", {},
                               after_claim=interrupt_after_claim)
        with TestClient(create_app(self.paths)) as client:
            runs = client.get(f"/cases/{case_id}/runs").json()["runs"]
            self.assertEqual(runs[0]["status"], "running")
            self.assertTrue(runs[0]["incomplete"])
            self.assertEqual(runs[0]["verification"], "pending")
            repeat = client.post(f"/cases/{case_id}/runs",
                                 headers={"Idempotency-Key": "interrupted"},
                                 json={"operation": "transaction"})
            self.assertEqual(repeat.status_code, 409)


if __name__ == "__main__":
    unittest.main()
