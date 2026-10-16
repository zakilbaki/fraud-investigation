"""Import PaySim par lots vers deux fichiers SQLite séparés."""

from __future__ import annotations

import csv
import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import polars as pl

from fraud_investigation.database import (
    APP_SCHEMA, EVALUATION_INDEXES, EVALUATION_SCHEMA, SEARCH_INDEXES,
)


COLUMNS = (
    "step", "type", "amount", "nameOrig", "oldbalanceOrg",
    "newbalanceOrig", "nameDest", "oldbalanceDest", "newbalanceDest",
    "isFraud", "isFlaggedFraud",
)
DECIMAL_POSITIONS = (2, 4, 5, 7, 8)
TRANSACTION_TYPES = {"CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
INTEGER_PATTERN = re.compile(r"[0-9]+\Z")


@dataclass(frozen=True)
class ImportResult:
    status: str
    source_sha256: str
    transactions: int
    accounts: int
    labels: int


def _fingerprint(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    newline_count = 0
    last_byte = b""
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
            newline_count += chunk.count(b"\n")
            last_byte = chunk[-1:]
    physical_lines = newline_count + (last_byte != b"\n")
    if physical_lines < 2:
        raise ValueError("CSV vide ou sans transaction")
    return digest.hexdigest(), physical_lines - 1


def _check_header(path: Path) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        header = next(csv.reader(source), None)
    if tuple(header or ()) != COLUMNS:
        raise ValueError(f"En-tête PaySim incompatible : {header!r}")


def stable_transaction_id(source_sha256: str, source_line_number: int) -> bytes:
    """128 bits du SHA-256 de l'empreinte source et de la ligne physique."""
    if not SHA256_PATTERN.fullmatch(source_sha256) or source_line_number < 2:
        raise ValueError("Provenance invalide pour l'identifiant de transaction")
    material = bytes.fromhex(source_sha256) + source_line_number.to_bytes(8, "big")
    return hashlib.sha256(material).digest()[:16]


def _validate_row(row: tuple[object, ...], line_number: int) -> tuple[object, ...]:
    if len(row) != len(COLUMNS) or any(not isinstance(value, str) or not value for value in row):
        raise ValueError(f"Ligne {line_number} : champ absent ou non textuel")
    step = row[0]
    if not INTEGER_PATTERN.fullmatch(step) or int(step) <= 0:
        raise ValueError(f"Ligne {line_number} : step invalide {step!r}")
    if row[1] not in TRANSACTION_TYPES:
        raise ValueError(f"Ligne {line_number} : type de transaction inconnu {row[1]!r}")
    for position in DECIMAL_POSITIONS:
        value = row[position]
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Ligne {line_number} : valeur décimale invalide {value!r}") from exc
        if not decimal_value.is_finite() or decimal_value < 0:
            raise ValueError(f"Ligne {line_number} : valeur décimale invalide {value!r}")
    if row[9] not in ("0", "1") or row[10] not in ("0", "1"):
        raise ValueError(f"Ligne {line_number} : label hors de {{0, 1}}")
    return row


def _connect_build(path: Path, schema: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    # Ces fichiers ne seront publiés qu'après validation. Un arrêt laisse .partial.
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("PRAGMA journal_mode = OFF")
    connection.execute("PRAGMA synchronous = OFF")
    connection.executescript(schema)
    return connection


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _verify_labels_match(app: sqlite3.Connection, expected_rows: int) -> int:
    labels = _count(app, "evaluation.labels")
    if labels != expected_rows:
        raise RuntimeError("Effectifs transactions et labels différents")
    missing_labels = app.execute("""
        SELECT 1 FROM transactions AS t
        LEFT JOIN evaluation.labels AS l ON l.transaction_id = t.transaction_id
        WHERE l.transaction_id IS NULL OR l.source_line_number != t.source_line_number
        LIMIT 1
    """).fetchone()
    missing_transactions = app.execute("""
        SELECT 1 FROM evaluation.labels AS l
        LEFT JOIN transactions AS t ON t.transaction_id = l.transaction_id
        WHERE t.transaction_id IS NULL OR t.source_line_number != l.source_line_number
        LIMIT 1
    """).fetchone()
    if missing_labels or missing_transactions:
        raise RuntimeError("Identifiants de transactions et de labels incompatibles")
    return labels


def _verify_existing(
    db_path: Path, labels_path: Path, fingerprint: str, expected_rows: int
) -> ImportResult:
    if not db_path.is_file() or not labels_path.is_file():
        raise RuntimeError("Import incomplet : base applicative ou fichier de labels absent")
    with sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True) as app:
        row = app.execute(
            "SELECT source_sha256 FROM transactions WHERE source_line_number = 2"
        ).fetchone()
        if row is None or row[0] != bytes.fromhex(fingerprint):
            raise RuntimeError("Source incompatible avec la base existante ; aucune donnée modifiée")
        transactions = _count(app, "transactions")
        accounts = _count(app, "accounts")
        last_line = app.execute("SELECT MAX(source_line_number) FROM transactions").fetchone()[0]
        if transactions != expected_rows or last_line != expected_rows + 1:
            raise RuntimeError("Import incomplet dans la base applicative")
        app.execute("ATTACH DATABASE ? AS evaluation", (str(labels_path),))
        try:
            labels = _verify_labels_match(app, transactions)
        finally:
            app.execute("DETACH DATABASE evaluation")
    return ImportResult("already_imported", fingerprint, transactions, accounts, labels)


def _verify_build(app: sqlite3.Connection, labels_path: Path, expected_rows: int) -> tuple[int, int]:
    app.execute("PRAGMA foreign_keys = ON")
    if app.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("Activation des clés étrangères impossible")
    transactions = _count(app, "transactions")
    accounts = _count(app, "accounts")
    if transactions != expected_rows:
        raise RuntimeError(f"Import incomplet : {transactions} transactions pour {expected_rows} lignes")
    if app.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("Contraintes relationnelles non respectées")
    if app.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError("Contrôle d'intégrité de la base applicative échoué")
    app.execute("ATTACH DATABASE ? AS evaluation", (str(labels_path),))
    try:
        _verify_labels_match(app, transactions)
    finally:
        app.execute("DETACH DATABASE evaluation")
    return transactions, accounts


def import_paysim(
    csv_path: Path | str,
    db_path: Path | str,
    labels_path: Path | str,
    *,
    expected_sha256: str | None = None,
    batch_size: int = 20_000,
) -> ImportResult:
    """Créer deux bases sur fichiers temporaires, puis les publier après vérification."""
    source, app_file, evaluation_file = map(Path, (csv_path, db_path, labels_path))
    if not source.is_file():
        raise FileNotFoundError(source)
    if len({p.resolve() for p in (source, app_file, evaluation_file)}) != 3:
        raise ValueError("Les chemins source, application et évaluation doivent être distincts")
    if batch_size <= 0:
        raise ValueError("batch_size doit être positif")
    _check_header(source)
    fingerprint, expected_rows = _fingerprint(source)
    if expected_sha256 is not None and expected_sha256.lower() != fingerprint:
        raise ValueError("Empreinte source différente de l'empreinte attendue")

    app_partial = app_file.with_name(app_file.name + ".partial")
    evaluation_partial = evaluation_file.with_name(evaluation_file.name + ".partial")
    if app_partial.exists() or evaluation_partial.exists():
        raise RuntimeError("Import incomplet détecté : fichiers .partial à examiner avant de relancer")
    if app_file.exists() or evaluation_file.exists():
        return _verify_existing(app_file, evaluation_file, fingerprint, expected_rows)

    app_file.parent.mkdir(parents=True, exist_ok=True)
    evaluation_file.parent.mkdir(parents=True, exist_ok=True)
    app = _connect_build(app_partial, APP_SCHEMA)
    evaluation = _connect_build(evaluation_partial, EVALUATION_SCHEMA)
    source_bytes = bytes.fromhex(fingerprint)
    processed = 0
    try:
        frame = pl.scan_csv(
            source,
            schema_overrides={name: pl.String for name in COLUMNS},
            infer_schema=False,
            low_memory=True,
            ignore_errors=False,
        )
        for batch in frame.collect_batches(
            chunk_size=batch_size, maintain_order=True, engine="streaming"
        ):
            transactions: list[tuple[object, ...]] = []
            labels: list[tuple[object, ...]] = []
            for row in batch.iter_rows():
                line_number = processed + len(transactions) + 2
                values = _validate_row(row, line_number)
                transaction_id = stable_transaction_id(fingerprint, line_number)
                transactions.append((
                    line_number, transaction_id, source_bytes, int(values[0]),
                    values[1], values[2], values[3], values[4], values[5],
                    values[6], values[7], values[8],
                ))
                labels.append((line_number, transaction_id, int(values[9]), int(values[10])))
            with app:
                app.executemany("""
                    INSERT INTO transactions (
                        source_line_number, transaction_id, source_sha256, step,
                        type, amount, name_orig, oldbalance_org, newbalance_orig,
                        name_dest, oldbalance_dest, newbalance_dest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, transactions)
            with evaluation:
                evaluation.executemany("""
                    INSERT INTO labels (
                        source_line_number, transaction_id, isFraud, isFlaggedFraud
                    ) VALUES (?, ?, ?, ?)
                """, labels)
            processed += len(transactions)
        if processed != expected_rows:
            raise RuntimeError(
                f"Numérotation physique incompatible : {processed} enregistrements, "
                f"{expected_rows} lignes attendues. Vérifier les retours ligne dans les champs CSV."
            )
        # Le tri unique intervient une fois, après la lecture, plutôt qu'à chaque ligne.
        with app:
            app.execute("""
                INSERT INTO accounts(account_id)
                SELECT name_orig AS account_id FROM transactions
                UNION
                SELECT name_dest AS account_id FROM transactions
            """)
        app.executescript(SEARCH_INDEXES)
        evaluation.executescript(EVALUATION_INDEXES)
        transactions_count, accounts_count = _verify_build(app, evaluation_partial, expected_rows)
        with evaluation:
            if evaluation.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("Contrôle d'intégrité du fichier de labels échoué")
        app.execute("PRAGMA journal_mode = DELETE")
        evaluation.execute("PRAGMA journal_mode = DELETE")
        app.close()
        evaluation.close()
        os.replace(evaluation_partial, evaluation_file)
        os.replace(app_partial, app_file)
        return ImportResult(
            "imported", fingerprint, transactions_count, accounts_count, transactions_count
        )
    finally:
        app.close()
        evaluation.close()
