"""Schéma local et consultations de transactions PaySim."""

from __future__ import annotations

import sqlite3
from pathlib import Path


APP_SCHEMA = """
CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY CHECK (length(account_id) > 0)
) WITHOUT ROWID;

CREATE TABLE transactions (
    source_line_number INTEGER PRIMARY KEY CHECK (source_line_number >= 2),
    transaction_id BLOB NOT NULL CHECK (length(transaction_id) = 16),
    source_sha256 BLOB NOT NULL CHECK (length(source_sha256) = 32),
    step INTEGER NOT NULL CHECK (step > 0),
    type TEXT NOT NULL CHECK (length(type) > 0),
    amount TEXT NOT NULL CHECK (length(amount) > 0),
    name_orig TEXT NOT NULL REFERENCES accounts(account_id),
    oldbalance_org TEXT NOT NULL CHECK (length(oldbalance_org) > 0),
    newbalance_orig TEXT NOT NULL CHECK (length(newbalance_orig) > 0),
    name_dest TEXT NOT NULL REFERENCES accounts(account_id),
    oldbalance_dest TEXT NOT NULL CHECK (length(oldbalance_dest) > 0),
    newbalance_dest TEXT NOT NULL CHECK (length(newbalance_dest) > 0)
);

CREATE TABLE investigation_cases (
    case_id TEXT PRIMARY KEY CHECK (length(case_id) > 0),
    transaction_id BLOB NOT NULL REFERENCES transactions(transaction_id),
    status TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'closed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE investigation_events (
    event_id TEXT PRIMARY KEY CHECK (length(event_id) > 0),
    case_id TEXT NOT NULL REFERENCES investigation_cases(case_id),
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (length(event_type) > 0),
    details_json TEXT NOT NULL
);
"""

EVALUATION_SCHEMA = """
CREATE TABLE labels (
    source_line_number INTEGER PRIMARY KEY CHECK (source_line_number >= 2),
    transaction_id BLOB NOT NULL CHECK (length(transaction_id) = 16),
    isFraud INTEGER NOT NULL CHECK (isFraud IN (0, 1)),
    isFlaggedFraud INTEGER NOT NULL CHECK (isFlaggedFraud IN (0, 1))
);
"""

SEARCH_INDEXES = """
CREATE UNIQUE INDEX transactions_id_unique ON transactions(transaction_id);
CREATE INDEX transactions_orig_step_id
ON transactions(name_orig, step DESC, transaction_id);
CREATE INDEX transactions_dest_step_id
ON transactions(name_dest, step DESC, transaction_id);
CREATE INDEX investigation_events_case_time
ON investigation_events(case_id, occurred_at, event_id);
"""

EVALUATION_INDEXES = """
CREATE UNIQUE INDEX labels_id_unique ON labels(transaction_id);
"""

TRANSACTION_FIELDS = """
transaction_id, source_sha256, source_line_number, step, type, amount,
name_orig, oldbalance_org, newbalance_orig, name_dest,
oldbalance_dest, newbalance_dest
"""

PUBLIC_TRANSACTION_KEYS = (
    "transaction_id", "source_sha256", "source_line_number", "step", "type",
    "amount", "name_orig", "oldbalance_org", "name_dest", "oldbalance_dest",
)


def public_transaction(transaction: dict[str, object]) -> dict[str, object]:
    """Ne conserver que les faits disponibles avant exécution de la transaction."""
    return {key: transaction[key] for key in PUBLIC_TRANSACTION_KEYS}


def readonly_sqlite_uri(path: Path | str) -> str:
    """Encoder le chemin du fichier avant d'ajouter le mode URI SQLite."""
    return Path(path).resolve().as_uri() + "?mode=ro"


def open_readonly(path: Path | str) -> sqlite3.Connection:
    """Ouvrir une base existante sans autoriser sa création ni sa modification."""
    database = Path(path).resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(readonly_sqlite_uri(database), uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _transaction_dict(row: sqlite3.Row) -> dict[str, object]:
    result = dict(row)
    result["transaction_id"] = result["transaction_id"].hex()
    result["source_sha256"] = result["source_sha256"].hex()
    return result


def get_transaction(connection: sqlite3.Connection, transaction_id: str) -> dict[str, object] | None:
    """Retrouver une transaction par son identifiant hexadécimal de 32 caractères."""
    if len(transaction_id) != 32:
        raise ValueError("transaction_id doit contenir 32 caractères hexadécimaux")
    try:
        identifier = bytes.fromhex(transaction_id)
    except ValueError as exc:
        raise ValueError("transaction_id doit être hexadécimal") from exc
    row = connection.execute(
        f"SELECT {TRANSACTION_FIELDS} FROM transactions WHERE transaction_id = ?",
        (identifier,),
    ).fetchone()
    return None if row is None else _transaction_dict(row)


def get_scoring_transaction(connection: sqlite3.Connection, transaction_id: str) -> sqlite3.Row | None:
    """Lire seulement les champs nécessaires au score et à la provenance."""
    if not isinstance(transaction_id, str) or len(transaction_id) != 32:
        raise ValueError("transaction_id doit contenir 32 caractères hexadécimaux")
    try:
        identifier = bytes.fromhex(transaction_id)
    except ValueError as exc:
        raise ValueError("transaction_id doit être hexadécimal") from exc
    return connection.execute(
        """SELECT transaction_id, source_sha256, step, type, amount,
                  oldbalance_org, name_dest
           FROM transactions WHERE transaction_id = ?""",
        (identifier,),
    ).fetchone()


def count_prior_receipts(connection: sqlite3.Connection, name_dest: str, step: int) -> int:
    """Compter les transactions antérieures, sans limite ni ordre intra-step."""
    if not name_dest or isinstance(step, bool) or not isinstance(step, int) or step <= 0:
        raise ValueError("Destinataire ou step invalide")
    return int(connection.execute(
        "SELECT COUNT(*) FROM transactions WHERE name_dest = ? AND step < ?",
        (name_dest, step),
    ).fetchone()[0])


def get_account_transactions(
    connection: sqlite3.Connection,
    account_id: str,
    before_step: int,
    limit: int = 50,
    min_step: int | None = None,
) -> list[dict[str, object]]:
    """Lister les transactions d'un compte avant un step, sans ordre intra-step temporel."""
    if not account_id:
        raise ValueError("account_id ne peut pas être vide")
    if isinstance(before_step, bool) or not isinstance(before_step, int) or before_step <= 0:
        raise ValueError("before_step doit être un entier positif")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("limit doit être compris entre 1 et 500")
    if min_step is not None and (isinstance(min_step, bool) or not isinstance(min_step, int)
                                 or not 1 <= min_step <= before_step):
        raise ValueError("min_step doit être un entier positif inférieur ou égal à before_step")
    rows = connection.execute(
        f"""SELECT {TRANSACTION_FIELDS}
            FROM transactions
            WHERE (name_orig = ? OR name_dest = ?) AND step < ? AND step >= ?
            ORDER BY step DESC, transaction_id ASC
            LIMIT ?""",
        (account_id, account_id, before_step, min_step or 1, limit),
    ).fetchall()
    return [_transaction_dict(row) for row in rows]
