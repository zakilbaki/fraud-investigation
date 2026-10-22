"""History access contracts on explicitly synthetic transactions, without labels."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from fraud_investigation.copilot_api import create_copilot_app
from fraud_investigation.database import APP_SCHEMA, SEARCH_INDEXES
from scripts.export_copilot_openapi import HISTORY_TEMPLATE, export


class CopilotHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "app.sqlite"
        self.key = "synthetic-history-test-key-with-at-least-32-characters"
        self.headers = {"X-API-Key": self.key}
        with sqlite3.connect(self.database) as db:
            db.executescript(APP_SCHEMA)
            db.executemany("INSERT INTO accounts VALUES (?)", [(a,) for a in ("A", "B", "C", "EMPTY")])
            for line, step, origin, recipient in (
                (2, 1, "A", "C"), (3, 2, "C", "A"), (4, 2, "B", "C"),
                (5, 3, "A", "B"), (6, 3, "A", "A"), (7, 4, "A", "B"),
                (8, 4, "C", "A"), (9, 5, "B", "A"), (10, 4, "B", "C"),
            ):
                db.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, 'TRANSFER', "
                           "'10.00', ?, '20.00', '10.00', ?, '0.00', '10.00')",
                           (line, line.to_bytes(16, "big"), b"\x00" * 32, step, origin, recipient))
            db.executescript(SEARCH_INDEXES)

    def tearDown(self):
        self.directory.cleanup()

    def app(self, missing=False):
        return create_copilot_app(
            self.database.with_name("missing.sqlite") if missing else self.database,
            api_key=self.key, model_path=self.database.with_suffix(".joblib"),
            manifest_path=self.database.with_suffix(".json"),
        )

    def anchor_url(self, role="sender", line=7):
        return f"/transactions/{line.to_bytes(16, 'big').hex()}/{role}-history"

    def test_all_history_tools_require_authentication(self):
        with TestClient(self.app()) as client:
            for url in (self.anchor_url(), self.anchor_url("recipient"),
                        "/accounts/A/transactions?before_step=4"):
                self.assertEqual(client.get(url).status_code, 401)
                response = client.get(url, headers={"X-API-Key": "incorrect"})
                self.assertEqual(response.status_code, 401)
                self.assertNotIn(self.key, response.text)

    def test_transaction_anchor_derives_account_and_excludes_same_step_future(self):
        with TestClient(self.app()) as client:
            for role, account, lines in (("sender", "A", [5, 6, 3, 2]),
                                          ("recipient", "B", [5, 4])):
                response = client.get(self.anchor_url(role), headers=self.headers,
                                      params={"before_step": 100, "account_id": "C"})
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["account_id"], account)
                self.assertEqual(body["account_role"], role)
                self.assertEqual(body["anchor_transaction_id"], (7).to_bytes(16, "big").hex())
                self.assertEqual(body["before_step"], 4)
                self.assertEqual(body["min_step"], 1)
                self.assertEqual(body["returned_count"], len(lines))
                self.assertEqual([r["source_line_number"] for r in body["transactions"]], lines)
                self.assertFalse(body["truncated"])
                self.assertTrue(all(r["step"] < 4 for r in body["transactions"]))
                self.assertEqual(len({r["transaction_id"] for r in body["transactions"]}), len(lines))
            self.assertEqual(client.post("/score", headers=self.headers,
                                          json={"transaction_id": (7).to_bytes(16, "big").hex()}).status_code, 503)

    def test_direct_account_matches_anchored_history_and_covers_both_roles(self):
        with TestClient(self.app()) as client:
            for role, account in (("sender", "A"), ("recipient", "B")):
                anchored = client.get(self.anchor_url(role), headers=self.headers).json()
                direct = client.get(f"/accounts/{account}/transactions?before_step=4",
                                    headers=self.headers)
                self.assertEqual(direct.status_code, 200)
                self.assertEqual(direct.json(), {k: v for k, v in anchored.items()
                                                 if k not in ("anchor_transaction_id", "account_role")})

    def test_window_boundary_limit_truncation_and_exact_decimal_fields(self):
        with TestClient(self.app()) as client:
            for url in (self.anchor_url(), "/accounts/A/transactions"):
                response = client.get(url, headers=self.headers,
                                      params={"before_step": 4, "lookback_steps": 2, "limit": 2})
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["min_step"], 2)
                self.assertEqual(body["returned_count"], 2)
                self.assertTrue(body["truncated"])
                self.assertEqual([r["source_line_number"] for r in body["transactions"]], [5, 6])
                for row in body["transactions"]:
                    self.assertEqual(row["amount"], "10.00")
                    self.assertEqual(set(row), {"transaction_id", "source_sha256", "source_line_number",
                                               "step", "type", "amount", "name_orig", "oldbalance_org",
                                               "name_dest", "oldbalance_dest"})
            full = client.get(self.anchor_url(), headers=self.headers,
                              params={"lookback_steps": 2, "limit": 100}).json()
            self.assertEqual([r["source_line_number"] for r in full["transactions"]], [5, 6, 3])
            self.assertFalse(full["truncated"])

    def test_empty_history_is_distinct_from_unknown_account_or_transaction(self):
        with TestClient(self.app()) as client:
            first = client.get(self.anchor_url(line=2), headers=self.headers)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["transactions"], [])
            empty = client.get("/accounts/EMPTY/transactions?before_step=4", headers=self.headers)
            self.assertEqual(empty.status_code, 200)
            self.assertEqual(empty.json()["returned_count"], 0)
            self.assertFalse(empty.json()["truncated"])
            self.assertEqual(client.get("/accounts/unknown/transactions?before_step=4",
                                        headers=self.headers).status_code, 404)
            self.assertEqual(client.get(self.anchor_url(line=999), headers=self.headers).status_code, 404)
            self.assertEqual(client.get("/transactions/0/sender-history", headers=self.headers).status_code, 400)

    def test_bounds_required_cutoff_and_invalid_accounts(self):
        with TestClient(self.app()) as client:
            for url in (self.anchor_url(), self.anchor_url("recipient"), "/accounts/A/transactions"):
                for field, value in (("limit", 0), ("limit", 101), ("lookback_steps", 0),
                                     ("lookback_steps", 169)):
                    params = {"before_step": 4, field: value}
                    self.assertEqual(client.get(url, headers=self.headers, params=params).status_code, 422)
            self.assertEqual(client.get("/accounts/A/transactions", headers=self.headers).status_code, 422)
            for cutoff in (0, 1_000_001, "invalid"):
                self.assertEqual(client.get("/accounts/A/transactions", headers=self.headers,
                                            params={"before_step": cutoff}).status_code, 422)
            for account in (" ", "A" * 129):
                self.assertEqual(client.get(f"/accounts/{account}/transactions?before_step=4",
                                            headers=self.headers).status_code, 400)

    def test_missing_database_and_parameterized_account_lookup(self):
        with TestClient(self.app(missing=True)) as client:
            for url in (self.anchor_url(), self.anchor_url("recipient"),
                        "/accounts/A/transactions?before_step=4"):
                response = client.get(url, headers=self.headers)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(str(self.database.parent), response.text)
        with TestClient(self.app()) as client:
            response = client.get("/accounts/A' OR '1'='1/transactions?before_step=4", headers=self.headers)
            self.assertEqual(response.status_code, 404)
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 9)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM investigation_cases").fetchone()[0], 0)

    def test_history_export_contains_only_three_authenticated_described_get_operations(self):
        output = Path(self.directory.name) / "history.swagger.json"
        export("https://tunnel.example.org", output, tool="history")
        spec = json.loads(output.read_text())
        self.assertEqual(spec["swagger"], "2.0")
        self.assertEqual(spec["host"], "tunnel.example.org")
        self.assertEqual(set(spec["paths"]), {
            "/transactions/{transaction_id}/sender-history",
            "/transactions/{transaction_id}/recipient-history",
            "/accounts/{account_id}/transactions",
        })
        ids = []
        for path, methods in spec["paths"].items():
            self.assertEqual(set(methods), {"get"})
            operation = methods["get"]
            ids.append(operation["operationId"])
            self.assertEqual(operation["security"], [{"ApiKeyAuth": []}])
            self.assertTrue(all(p["description"] for p in operation["parameters"]))
            self.assertTrue(all(r["description"] for r in operation["responses"].values()))
            params = {p["name"]: p for p in operation["parameters"]}
            self.assertEqual(params["limit"]["maximum"], 100)
            self.assertEqual(params["lookback_steps"]["maximum"], 168)
            self.assertEqual("before_step" in params, path.startswith("/accounts/"))
            if "before_step" in params:
                self.assertTrue(params["before_step"]["required"])
        self.assertEqual(len(set(ids)), 3)
        for schema in spec["definitions"].values():
            self.assertTrue(all(p["description"] for p in schema["properties"].values()))
        self.assertNotIn(self.key, output.read_text())
        self.assertIn(".invalid", HISTORY_TEMPLATE.read_text())
