import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from fraud_investigation.database import APP_SCHEMA, SEARCH_INDEXES
from fraud_investigation.transaction_api import create_transaction_app


class TransactionApiTests(unittest.TestCase):
    def test_existing_unknown_invalid_and_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "transactions.sqlite"
            transaction_id = (2).to_bytes(16, "big").hex()
            with sqlite3.connect(database) as connection:
                connection.executescript(APP_SCHEMA)
                connection.executemany(
                    "INSERT INTO accounts(account_id) VALUES (?)", [("O1",), ("D1",)]
                )
                connection.execute(
                    "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (2, bytes.fromhex(transaction_id), b"\x00" * 32, 1, "TRANSFER",
                     "10.00", "O1", "20.00", "10.00", "D1", "0.00", "10.00"),
                )
                connection.executescript(SEARCH_INDEXES)

            with TestClient(create_transaction_app(database)) as client:
                response = client.get(f"/transactions/{transaction_id}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["transaction_id"], transaction_id)
                self.assertEqual(response.json()["amount"], "10.00")
                self.assertEqual(response.json()["source_line_number"], 2)
                self.assertNotIn("newbalance_orig", response.json())
                self.assertNotIn("newbalance_dest", response.json())
                self.assertNotIn("isFraud", response.json())
                self.assertNotIn("isFlaggedFraud", response.json())
                self.assertEqual(client.get(f"/transactions/{'f' * 32}").status_code, 404)
                self.assertEqual(
                    client.get(f"/transactions/{'f' * 32}").json()["detail"],
                    "Transaction introuvable",
                )
                self.assertEqual(client.get("/transactions/invalid").status_code, 400)
                self.assertEqual(client.get(f"/transactions/{'g' * 32}").status_code, 400)

            with TestClient(create_transaction_app(database.with_name("missing.sqlite"))) as client:
                self.assertEqual(client.get(f"/transactions/{transaction_id}").status_code, 503)

    def test_history_is_bounded_prior_and_unique_for_self_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "app.sqlite"
            with sqlite3.connect(database) as connection:
                connection.executescript(APP_SCHEMA)
                connection.execute("INSERT INTO accounts VALUES ('A')")
                for line, step in [(2, 1), (3, 2), (4, 2), (5, 3)]:
                    connection.execute(
                        "INSERT INTO transactions VALUES (?, ?, ?, ?, 'TRANSFER', '1.00', "
                        "'A', '2.00', '1.00', 'A', '0.00', '1.00')",
                        (line, line.to_bytes(16, "big"), b"\x00" * 32, step),
                    )
                connection.executescript(SEARCH_INDEXES)
            with TestClient(create_transaction_app(database)) as client:
                url = "/accounts/A/transactions?before_step=3&limit=2"
                response = client.get(url)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertTrue(data["truncated"])
                self.assertEqual(len(data["transactions"]), 2)
                self.assertEqual([row["step"] for row in data["transactions"]], [2, 2])
                self.assertEqual(len({row["transaction_id"] for row in data["transactions"]}), 2)
                self.assertNotIn("newbalance_orig", data["transactions"][0])
                self.assertNotIn("isFraud", data["transactions"][0])
                full = client.get("/accounts/A/transactions?before_step=3&limit=3").json()
                self.assertFalse(full["truncated"])
                self.assertEqual(len(full["transactions"]), 3)
                self.assertEqual(client.get("/accounts/A/transactions?limit=2").status_code, 422)
                self.assertEqual(client.get("/accounts/A/transactions?before_step=3&limit=101").status_code, 422)
                window = client.get("/accounts/A/transactions?before_step=3&lookback_steps=1").json()
                self.assertEqual([row["step"] for row in window["transactions"]], [2, 2])
                self.assertEqual(client.get("/accounts/A/transactions?before_step=3&lookback_steps=169").status_code, 422)
                self.assertEqual(client.get("/accounts/A/transactions?before_step=1").json()["transactions"], [])


if __name__ == "__main__":
    unittest.main()
