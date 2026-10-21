import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from fraud_investigation.api import create_app
from fraud_investigation.database import APP_SCHEMA, SEARCH_INDEXES
from fraud_investigation.scoring_service import ScoringPaths


class CaseApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "app.sqlite"
        self.transaction_id = (2).to_bytes(16, "big").hex()
        with sqlite3.connect(self.database) as connection:
            connection.executescript(APP_SCHEMA)
            connection.executemany("INSERT INTO accounts VALUES (?)", [("A",), ("B",)])
            connection.execute(
                "INSERT INTO transactions VALUES (?, ?, ?, 1, 'TRANSFER', '10.00', "
                "'A', '20.00', '10.00', 'B', '0.00', '10.00')",
                (2, bytes.fromhex(self.transaction_id), b"\x00" * 32),
            )
            connection.executescript(SEARCH_INDEXES)
        self.paths = ScoringPaths(self.database, self.database.with_name("missing.joblib"),
                                  self.database.with_name("missing.json"))

    def tearDown(self):
        self.directory.cleanup()

    def test_missing_model_does_not_disable_facts_or_cases(self):
        with TestClient(create_app(self.paths)) as client:
            self.assertEqual(client.get(f"/transactions/{self.transaction_id}").status_code, 200)
            self.assertEqual(client.get("/accounts/A/transactions?before_step=2").status_code, 200)
            self.assertEqual(client.get("/health").status_code, 503)
            self.assertEqual(client.post("/score", json={"transaction_id": self.transaction_id}).status_code, 503)
            self.assertEqual(client.get("/openapi.json").status_code, 200)
            openapi = client.get("/openapi.json").json()
            self.assertIn("/cases", openapi["paths"])
            self.assertNotIn("newbalance_orig", openapi["components"]["schemas"]["TransactionResponse"]["properties"])

    def test_case_event_idempotence_and_foreign_keys(self):
        headers = {"Idempotency-Key": "case-one"}
        with TestClient(create_app(self.paths)) as client:
            unknown = client.post("/cases", headers=headers,
                                  json={"transaction_id": "f" * 32})
            self.assertEqual(unknown.status_code, 404)
            created = client.post("/cases", headers=headers,
                                  json={"transaction_id": self.transaction_id})
            self.assertEqual(created.status_code, 201)
            case = created.json()
            self.assertEqual(client.post("/cases", headers=headers,
                                         json={"transaction_id": self.transaction_id}).json(), case)
            self.assertEqual(client.post("/cases", headers=headers,
                                         json={"transaction_id": "f" * 32}).status_code, 409)
            self.assertEqual(client.get(f"/cases/{case['case_id']}").json()["status"], "open")
            first = client.get(f"/cases/{case['case_id']}/events").json()
            self.assertEqual(len(first["events"]), 1)
            self.assertEqual(first["events"][0]["event_type"], "case_created")
            self.assertEqual(first["events"][0]["verification"], "verified_transaction_reference")
            event = {"event_type": "tool_result", "origin": "tool",
                     "content": {"observation": "simulation"}, "references": [self.transaction_id]}
            event_headers = {"Idempotency-Key": "event-one"}
            added = client.post(f"/cases/{case['case_id']}/events", headers=event_headers,
                                json=event)
            self.assertEqual(added.status_code, 201)
            self.assertEqual(added.json()["verification"], "caller_supplied")
            self.assertEqual(client.post(f"/cases/{case['case_id']}/events",
                                         headers=event_headers, json=event).json(), added.json())
            changed = {**event, "content": {"observation": "different"}}
            self.assertEqual(client.post(f"/cases/{case['case_id']}/events",
                                         headers=event_headers, json=changed).status_code, 409)
            limited = client.get(f"/cases/{case['case_id']}/events?limit=1").json()
            self.assertTrue(limited["truncated"])
            self.assertEqual(client.get("/cases/missing/events").status_code, 404)

        with TestClient(create_app(self.paths)) as client:
            self.assertEqual(client.post("/cases", headers=headers,
                                         json={"transaction_id": self.transaction_id}).json(), case)
            self.assertEqual(client.post(f"/cases/{case['case_id']}/events",
                                         headers=event_headers, json=event).json(), added.json())

        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM investigation_cases").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM investigation_events").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT amount FROM transactions").fetchone()[0], "10.00")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO investigation_events VALUES "
                                   "('bad', 'missing', '2026-01-01', 'comment', '{}')")

    def test_case_creation_rolls_back_if_first_event_fails(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TRIGGER fail_first_event BEFORE INSERT ON investigation_events "
                               "BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with TestClient(create_app(self.paths)) as client:
            response = client.post("/cases", headers={"Idempotency-Key": "atomic"},
                                   json={"transaction_id": self.transaction_id})
            self.assertEqual(response.status_code, 503)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM investigation_cases").fetchone()[0], 0)

    def test_migration_preserves_existing_case(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "INSERT INTO investigation_cases VALUES ('legacy', ?, 'open', '2026-01-01', '2026-01-01')",
                (bytes.fromhex(self.transaction_id),),
            )
            connection.execute(
                "INSERT INTO investigation_events VALUES "
                "('old-event', 'legacy', '2026-01-01', 'old_type', '{\"note\":\"existing\"}')"
            )
        with TestClient(create_app(self.paths)) as client:
            created = client.post("/cases", headers={"Idempotency-Key": "new"},
                                  json={"transaction_id": self.transaction_id})
            self.assertEqual(created.status_code, 201)
            self.assertEqual(client.get("/cases/legacy").status_code, 200)
            old_event = client.get("/cases/legacy/events").json()["events"][0]
            self.assertEqual(old_event["content"], {"note": "existing"})
            self.assertEqual(old_event["origin"], "legacy")
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM investigation_cases").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
