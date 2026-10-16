"""Petits CSV explicitement synthétiques pour les invariants de stockage."""

from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fraud_investigation.database import get_account_transactions, get_transaction, open_readonly
from fraud_investigation.importer import import_paysim, stable_transaction_id


HEADER = (
    "step", "type", "amount", "nameOrig", "oldbalanceOrg",
    "newbalanceOrig", "nameDest", "oldbalanceDest", "newbalanceDest",
    "isFraud", "isFlaggedFraud",
)


class ImporterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="fraud-test-")
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.csv = root / "synthetic.csv"
        self.database = root / "app.sqlite"
        self.labels = root / "evaluation" / "labels.sqlite"
        self.rows = [
            ("1", "TRANSFER", "1.00", "C1", "10.00", "9.00", "C2", "0.00", "1.00", "0", "0"),
            ("2", "PAYMENT", "0.00", "C1", "9.00", "9.00", "M1", "0.00", "0.00", "1", "0"),
            ("2", "PAYMENT", "0.00", "C1", "9.00", "9.00", "M1", "0.00", "0.00", "1", "0"),
            ("2", "CASH_IN", "2.50", "C3", "2.50", "0.00", "C1", "9.00", "11.50", "0", "1"),
            ("3", "TRANSFER", "3.00", "C1", "11.50", "8.50", "C4", "0.00", "3.00", "0", "0"),
            ("1", "DEBIT", "1.00", "C1", "8.50", "7.50", "C1", "8.50", "7.50", "0", "0"),
        ]
        with self.csv.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(HEADER)
            writer.writerows(self.rows)

    def test_import_queries_labels_and_idempotence(self) -> None:
        first = import_paysim(self.csv, self.database, self.labels, batch_size=2)
        self.assertEqual((first.status, first.transactions, first.accounts, first.labels),
                         ("imported", 6, 5, 6))
        with open_readonly(self.database) as app:
            app_tables = {row[0] for row in app.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )}
            self.assertEqual(app_tables, {
                "transactions", "accounts", "investigation_cases", "investigation_events"
            })
            fields = {row[1] for row in app.execute("PRAGMA table_info(transactions)")}
            self.assertNotIn("isFraud", fields)
            self.assertNotIn("isFlaggedFraud", fields)
            self.assertIsNone(app.execute("PRAGMA foreign_key_check").fetchone())

            ids = [row[0].hex() for row in app.execute(
                "SELECT transaction_id FROM transactions ORDER BY source_line_number"
            )]
            self.assertEqual(len(set(ids)), 6)
            self.assertEqual(ids[0], stable_transaction_id(first.source_sha256, 2).hex())
            self.assertNotEqual(ids[1], ids[2])
            self.assertEqual(get_transaction(app, ids[1])["amount"], "0.00")
            self.assertIsNone(get_transaction(app, "0" * 32))
            self.assertEqual(len(get_account_transactions(app, "C1", before_step=3)), 5)
            limited = get_account_transactions(app, "C1", before_step=3, limit=2)
            self.assertEqual(len(limited), 2)
            self.assertTrue(all(row["step"] < 3 for row in limited))
            self.assertEqual([row["step"] for row in limited], [2, 2])
            self.assertEqual(get_account_transactions(app, "C1", before_step=1), [])
            self.assertEqual(get_account_transactions(app, "unknown", before_step=4), [])

        with sqlite3.connect(self.labels) as evaluation:
            self.assertEqual(evaluation.execute("SELECT COUNT(*) FROM labels").fetchone()[0], 6)
            self.assertEqual(evaluation.execute("SELECT SUM(isFraud) FROM labels").fetchone()[0], 2)

        with sqlite3.connect(self.database) as app:
            app.execute("PRAGMA foreign_keys = ON")
            app.execute("""
                INSERT INTO investigation_cases(case_id, transaction_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, ("case-1", bytes.fromhex(ids[0]), "open", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"))
        second = import_paysim(self.csv, self.database, self.labels, batch_size=3)
        self.assertEqual(second.status, "already_imported")
        with sqlite3.connect(self.database) as app:
            self.assertEqual(app.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 6)
            self.assertEqual(app.execute("SELECT COUNT(*) FROM investigation_cases").fetchone()[0], 1)

        other_database = Path(self.directory.name) / "other.sqlite"
        other_labels = Path(self.directory.name) / "other-labels.sqlite"
        third = import_paysim(self.csv, other_database, other_labels, batch_size=4)
        self.assertEqual(third.source_sha256, first.source_sha256)
        with sqlite3.connect(other_database) as app:
            other_ids = [row[0].hex() for row in app.execute(
                "SELECT transaction_id FROM transactions ORDER BY source_line_number"
            )]
        self.assertEqual(ids, other_ids)

    def test_source_mismatch_does_not_replace_existing_database(self) -> None:
        import_paysim(self.csv, self.database, self.labels, batch_size=2)
        with self.csv.open("a", newline="", encoding="utf-8") as file:
            csv.writer(file).writerow(self.rows[0])
        with self.assertRaisesRegex(RuntimeError, "Source incompatible"):
            import_paysim(self.csv, self.database, self.labels, batch_size=2)
        with sqlite3.connect(self.database) as app:
            self.assertEqual(app.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 6)

    def test_same_count_labels_from_another_source_are_rejected(self) -> None:
        import_paysim(self.csv, self.database, self.labels, batch_size=2)
        other_source = Path(self.directory.name) / "other-source.csv"
        other_database = Path(self.directory.name) / "other-app.sqlite"
        other_labels = Path(self.directory.name) / "other-labels.sqlite"
        other_rows = list(self.rows)
        other_rows[0] = (*other_rows[0][:2], "1.01", *other_rows[0][3:])
        with other_source.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(HEADER)
            writer.writerows(other_rows)
        import_paysim(other_source, other_database, other_labels, batch_size=2)

        app_before = self.database.read_bytes()
        labels_before = other_labels.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Identifiants de transactions et de labels incompatibles"):
            import_paysim(self.csv, self.database, other_labels, batch_size=2)
        self.assertEqual(self.database.read_bytes(), app_before)
        self.assertEqual(other_labels.read_bytes(), labels_before)

    def test_invalid_amount_leaves_partial_import_visible(self) -> None:
        rows = list(self.rows)
        rows[-1] = (*rows[-1][:2], "-1", *rows[-1][3:])
        with self.csv.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(HEADER)
            writer.writerows(rows)
        with self.assertRaisesRegex(ValueError, "valeur décimale invalide"):
            import_paysim(self.csv, self.database, self.labels, batch_size=2)
        self.assertFalse(self.database.exists())
        self.assertTrue(self.database.with_name("app.sqlite.partial").exists())
        with self.assertRaisesRegex(RuntimeError, "Import incomplet"):
            import_paysim(self.csv, self.database, self.labels, batch_size=2)


if __name__ == "__main__":
    unittest.main()
