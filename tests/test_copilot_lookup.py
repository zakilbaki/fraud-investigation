import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from fraud_investigation.copilot_api import API_KEY_ENV, create_copilot_app
from fraud_investigation.database import APP_SCHEMA, SEARCH_INDEXES
from scripts.export_copilot_openapi import TEMPLATE, export


class CopilotLookupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "app.sqlite"
        self.transaction_id = (2).to_bytes(16, "big").hex()
        self.key = "synthetic-test-secret-of-at-least-32-characters"
        with sqlite3.connect(self.database) as connection:
            connection.executescript(APP_SCHEMA)
            connection.executemany("INSERT INTO accounts VALUES (?)", [("A",), ("B",)])
            connection.execute(
                "INSERT INTO transactions VALUES (?, ?, ?, 1, 'TRANSFER', '10.00', "
                "'A', '20.00', '10.00', 'B', '0.00', '10.00')",
                (2, bytes.fromhex(self.transaction_id), b"\x00" * 32),
            )
            connection.executescript(SEARCH_INDEXES)

    def tearDown(self):
        self.directory.cleanup()

    def test_missing_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                create_copilot_app(self.database)
        with self.assertRaises(RuntimeError):
            create_copilot_app(self.database, api_key="short")

    def test_authentication_lookup_and_narrow_surface(self):
        with patch.dict(os.environ, {API_KEY_ENV: self.key}):
            app = create_copilot_app(self.database)
        with TestClient(app) as client:
            url = f"/transactions/{self.transaction_id}"
            self.assertEqual(client.get(url).status_code, 401)
            bad = client.get(url, headers={"X-API-Key": "wrong"})
            self.assertEqual(bad.status_code, 401)
            self.assertNotIn(self.key, bad.text)
            valid = client.get(url, headers={"X-API-Key": self.key})
            self.assertEqual(valid.status_code, 200)
            self.assertEqual(valid.json()["transaction_id"], self.transaction_id)
            self.assertEqual(valid.json()["amount"], "10.00")
            self.assertNotIn("newbalance_orig", valid.json())
            self.assertNotIn("newbalance_dest", valid.json())
            self.assertNotIn("isFraud", valid.json())
            self.assertNotIn("isFlaggedFraud", valid.json())
            self.assertEqual(client.get("/transactions/invalid").status_code, 401)
            self.assertEqual(client.get("/transactions/invalid", headers={"X-API-Key": self.key}).status_code, 400)
            self.assertEqual(client.get("/transactions/" + "f" * 32,
                                        headers={"X-API-Key": self.key}).status_code, 404)
            self.assertEqual(client.get("/cases").status_code, 401)
            self.assertEqual(client.get("/score").status_code, 405)
            self.assertEqual(set(app.openapi()["paths"]),
                             {"/transactions/{transaction_id}", "/score",
                              "/transactions/{transaction_id}/sender-history",
                              "/transactions/{transaction_id}/recipient-history",
                              "/accounts/{account_id}/transactions",
                              "/cases", "/cases/{case_id}", "/cases/{case_id}/runs",
                              "/cases/{case_id}/runs/{run_id}", "/cases/{case_id}/reports",
                              "/cases/{case_id}/reports/{version}"})
            self.assertEqual(client.get("/openapi.json").status_code, 404)
        with TestClient(create_copilot_app(self.database.with_name("missing.sqlite"),
                                           api_key=self.key)) as client:
            self.assertEqual(client.get(f"/transactions/{self.transaction_id}",
                                        headers={"X-API-Key": self.key}).status_code, 503)

    def test_swagger_v2_export_contains_only_lookup_and_no_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "transaction_lookup.swagger.json"
            export("https://tunnel.example.org", output)
            spec = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(spec["swagger"], "2.0")
            self.assertEqual(spec["host"], "tunnel.example.org")
            self.assertEqual(spec["schemes"], ["https"])
            self.assertEqual(list(spec["paths"]), ["/transactions/{transaction_id}"])
            self.assertEqual(list(spec["paths"]["/transactions/{transaction_id}"]), ["get"])
            operation = spec["paths"]["/transactions/{transaction_id}"]["get"]
            self.assertEqual(operation["operationId"], "getTransactionById")
            self.assertTrue(operation["summary"] and operation["description"])
            self.assertTrue(all(response["description"] for response in operation["responses"].values()))
            self.assertTrue(all(property_schema["description"] for property_schema in
                                spec["definitions"]["Transaction"]["properties"].values()))
            self.assertEqual(operation["security"], [{"ApiKeyAuth": []}])
            self.assertEqual(spec["securityDefinitions"]["ApiKeyAuth"]["name"], "X-API-Key")
            self.assertEqual(spec["securityDefinitions"]["ApiKeyAuth"]["in"], "header")
            self.assertEqual(set(spec["definitions"]["Transaction"]["properties"]), {
                "transaction_id", "source_sha256", "source_line_number", "step", "type",
                "amount", "name_orig", "oldbalance_org", "name_dest", "oldbalance_dest",
            })
            self.assertNotIn(self.key, output.read_text())
            self.assertIn(".invalid", TEMPLATE.read_text())
            for invalid_url in ("http://tunnel.example.org", "https://localhost",
                                "https://placeholder.invalid", "https://tunnel.example.org/path"):
                with self.assertRaises(ValueError):
                    export(invalid_url, output)


if __name__ == "__main__":
    unittest.main()
