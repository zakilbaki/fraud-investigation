"""Dossiers locaux, événements et idempotence durable."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


MIGRATION = """
CREATE TABLE IF NOT EXISTS investigation_idempotency (
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (operation, idempotency_key)
) WITHOUT ROWID;
"""


class CaseNotFound(Exception):
    pass


class TransactionNotFound(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _connect(path: Path | str) -> sqlite3.Connection:
    database = Path(path).resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(database, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        connection.close()
        raise sqlite3.OperationalError("Contraintes relationnelles indisponibles")
    return connection


def _digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _cached(connection: sqlite3.Connection, operation: str, key: str, digest: str):
    row = connection.execute(
        "SELECT request_sha256, response_json FROM investigation_idempotency "
        "WHERE operation = ? AND idempotency_key = ?", (operation, key)
    ).fetchone()
    if row is None:
        return None
    if row["request_sha256"] != digest:
        raise IdempotencyConflict
    return json.loads(row["response_json"])


def _remember(connection: sqlite3.Connection, operation: str, key: str,
              digest: str, result: dict[str, object]) -> None:
    connection.execute(
        "INSERT INTO investigation_idempotency VALUES (?, ?, ?, ?, ?)",
        (operation, key, digest, json.dumps(result, ensure_ascii=False), _utc()),
    )


def _event(row: sqlite3.Row) -> dict[str, object]:
    details = json.loads(row["details_json"])
    if not (isinstance(details, dict) and
            {"origin", "verification", "content", "references"} <= details.keys()):
        details = {"origin": "legacy", "verification": "caller_supplied",
                   "content": details if isinstance(details, dict) else {"value": details},
                   "references": []}
    return {"event_id": row["event_id"], "case_id": row["case_id"],
            "occurred_at": row["occurred_at"], "event_type": row["event_type"],
            "origin": details["origin"], "verification": details["verification"],
            "content": details["content"], "references": details["references"]}


def create_case(path: Path | str, transaction_id: str, key: str) -> dict[str, object]:
    operation = "create_case"
    digest = _digest({"transaction_id": transaction_id})
    with closing(_connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(MIGRATION)
        cached = _cached(connection, operation, key, digest)
        if cached is not None:
            connection.commit()
            return cached
        identifier = bytes.fromhex(transaction_id)
        if connection.execute(
            "SELECT 1 FROM transactions WHERE transaction_id = ?", (identifier,)
        ).fetchone() is None:
            raise TransactionNotFound
        now = _utc()
        case_id, event_id = uuid.uuid4().hex, uuid.uuid4().hex
        connection.execute(
            "INSERT INTO investigation_cases VALUES (?, ?, 'open', ?, ?)",
            (case_id, identifier, now, now),
        )
        details = {"origin": "backend", "verification": "verified_transaction_reference",
                   "content": {"transaction_id": transaction_id},
                   "references": [transaction_id]}
        connection.execute(
            "INSERT INTO investigation_events VALUES (?, ?, ?, 'case_created', ?)",
            (event_id, case_id, now, json.dumps(details)),
        )
        result = {"case_id": case_id, "transaction_id": transaction_id,
                  "status": "open", "created_at": now, "updated_at": now,
                  "first_event_id": event_id}
        _remember(connection, operation, key, digest, result)
        connection.commit()
        return result


def get_case(path: Path | str, case_id: str) -> dict[str, object]:
    with closing(_connect(path)) as connection:
        row = connection.execute(
            "SELECT * FROM investigation_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            raise CaseNotFound
        return {"case_id": row["case_id"], "transaction_id": row["transaction_id"].hex(),
                "status": row["status"], "created_at": row["created_at"],
                "updated_at": row["updated_at"]}


def add_event(path: Path | str, case_id: str, key: str,
              event_type: str, origin: str, content: dict[str, object],
              references: list[str]) -> dict[str, object]:
    operation = f"add_event:{case_id}"
    details = {"origin": origin, "verification": "caller_supplied",
               "content": content, "references": references}
    digest = _digest({"event_type": event_type, **details})
    with closing(_connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(MIGRATION)
        cached = _cached(connection, operation, key, digest)
        if cached is not None:
            connection.commit()
            return cached
        if connection.execute(
            "SELECT 1 FROM investigation_cases WHERE case_id = ?", (case_id,)
        ).fetchone() is None:
            raise CaseNotFound
        now, event_id = _utc(), uuid.uuid4().hex
        connection.execute(
            "INSERT INTO investigation_events VALUES (?, ?, ?, ?, ?)",
            (event_id, case_id, now, event_type, json.dumps(details, ensure_ascii=False)),
        )
        result = {"event_id": event_id, "case_id": case_id,
                  "occurred_at": now, "event_type": event_type, **details}
        _remember(connection, operation, key, digest, result)
        connection.commit()
        return result


def get_events(path: Path | str, case_id: str, limit: int) -> dict[str, object]:
    with closing(_connect(path)) as connection:
        if connection.execute(
            "SELECT 1 FROM investigation_cases WHERE case_id = ?", (case_id,)
        ).fetchone() is None:
            raise CaseNotFound
        rows = connection.execute(
            "SELECT * FROM investigation_events WHERE case_id = ? "
            "ORDER BY occurred_at, event_id LIMIT ?", (case_id, limit + 1)
        ).fetchall()
        return {"case_id": case_id, "limit": limit, "truncated": len(rows) > limit,
                "events": [_event(row) for row in rows[:limit]]}
