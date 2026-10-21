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


if __name__ == "__main__":
    unittest.main()
