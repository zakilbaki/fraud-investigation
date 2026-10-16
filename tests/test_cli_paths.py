"""Vérifier les chemins explicites depuis un dossier extérieur au dépôt."""

from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HEADER = (
    "step", "type", "amount", "nameOrig", "oldbalanceOrg",
    "newbalanceOrig", "nameDest", "oldbalanceDest", "newbalanceDest",
    "isFraud", "isFlaggedFraud",
)


class CliPathTest(unittest.TestCase):
    def test_audit_and_import_from_another_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fraud-cli-") as directory:
            outside = Path(directory)
            csv_path = outside / "source.csv"
            report_path = outside / "report.json"
            database_path = outside / "app" / "fraud.sqlite"
            labels_path = outside / "evaluation" / "labels.sqlite"
            with csv_path.open("w", newline="", encoding="utf-8") as source:
                writer = csv.writer(source)
                writer.writerow(HEADER)
                writer.writerow((1, "TRANSFER", "1.00", "C1", "2.00", "1.00", "C2", "0.00", "1.00", 0, 0))
                writer.writerow((2, "PAYMENT", "0.00", "C1", "1.00", "1.00", "M1", "0.00", "0.00", 1, 0))

            audit_result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts/audit_paysim.py"),
                 str(csv_path), "--output", str(report_path)],
                cwd=outside, capture_output=True, text=True, check=True,
            )
            self.assertIn("Audit écrit", audit_result.stdout)
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["row_count"], 2)

            import_result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts/import_paysim.py"),
                 str(csv_path), "--database", str(database_path),
                 "--labels", str(labels_path), "--batch-size", "1"],
                cwd=outside, capture_output=True, text=True, check=True,
            )
            self.assertIn("status=imported transactions=2", import_result.stdout)
            with sqlite3.connect(database_path) as database:
                self.assertEqual(database.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 2)
            with sqlite3.connect(labels_path) as labels:
                self.assertEqual(labels.execute("SELECT COUNT(*) FROM labels").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
