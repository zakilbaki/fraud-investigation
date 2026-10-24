"""Exécution contrôlée et conservation des résultats d'outils d'enquête."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Callable

from fraud_investigation.case_service import CaseNotFound, IdempotencyConflict, _connect, _digest, _utc
from fraud_investigation.database import (
    get_account_transactions, get_transaction, open_readonly, public_transaction,
)
from fraud_investigation.scoring_service import ArtifactError, ScoreService, ScoringDataError


RUN_TABLE = """
CREATE TABLE IF NOT EXISTS investigation_tool_runs (
    run_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES investigation_cases(case_id),
    idempotency_key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    operation TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'unavailable', 'failed')),
    result_json TEXT,
    error_json TEXT,
    UNIQUE (case_id, idempotency_key)
);
"""
RUN_INDEX = """
CREATE INDEX IF NOT EXISTS investigation_tool_runs_case_time
ON investigation_tool_runs(case_id, started_at, run_id);
"""

TOOL_VERSIONS = {
    "transaction": "transaction_lookup_v1",
    "score": "final_global_scoring_v1",
    "sender_history": "account_history_v1",
    "recipient_history": "account_history_v1",
}


class RunInProgress(Exception):
    pass


def _row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "run_id": row["run_id"], "case_id": row["case_id"],
        "operation": row["operation"], "tool_version": row["tool_version"],
        "parameters": json.loads(row["parameters_json"]),
        "started_at": row["started_at"], "finished_at": row["finished_at"],
        "status": row["status"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": json.loads(row["error_json"]) if row["error_json"] else None,
        "verification": "backend_executed" if row["status"] != "running" else "pending",
        "incomplete": row["status"] == "running",
    }


def _execute(path: Path | str, transaction_id: str, operation: str,
             parameters: dict[str, int], scorer: ScoreService | None) -> dict[str, object]:
    if operation not in TOOL_VERSIONS:
        raise ValueError("Opération inconnue")
    if operation == "score":
        if scorer is None:
            raise ArtifactError("Modèle indisponible")
        return scorer.score_transaction(transaction_id)
    with closing(open_readonly(path)) as connection:
        transaction = get_transaction(connection, transaction_id)
        if transaction is None:
            raise LookupError("Transaction du dossier introuvable")
        public = public_transaction(transaction)
        if operation == "transaction":
            return public
        account_id = public["name_orig"] if operation == "sender_history" else public["name_dest"]
        before_step = public["step"]
        lookback = parameters["lookback_steps"]
        limit = parameters["limit"]
        rows = get_account_transactions(
            connection, account_id, before_step, limit + 1,
            min_step=max(1, before_step - lookback),
        )
        return {
            "account_id": account_id, "before_step": before_step,
            "lookback_steps": lookback, "limit": limit,
            "truncated": len(rows) > limit,
            "transactions": [public_transaction(row) for row in rows[:limit]],
        }


def execute_and_record(
    path: Path | str, case_id: str, key: str, operation: str,
    parameters: dict[str, int], scorer: ScoreService | None = None,
    after_claim: Callable[[], None] | None = None,
) -> dict[str, object]:
    """Réserver la clé, exécuter sans verrou SQLite, puis enregistrer l'issue."""
    if operation not in TOOL_VERSIONS:
        raise ValueError("Opération inconnue")
    digest = _digest({"operation": operation, "parameters": parameters})
    with closing(_connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(RUN_TABLE)
        connection.execute(RUN_INDEX)
        case = connection.execute(
            "SELECT transaction_id FROM investigation_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if case is None:
            raise CaseNotFound
        prior = connection.execute(
            "SELECT * FROM investigation_tool_runs WHERE case_id = ? AND idempotency_key = ?",
            (case_id, key),
        ).fetchone()
        if prior is not None:
            if prior["request_sha256"] != digest:
                raise IdempotencyConflict
            if prior["status"] == "running":
                raise RunInProgress
            connection.commit()
            return _row(prior)
        run_id, started = uuid.uuid4().hex, _utc()
        connection.execute(
            "INSERT INTO investigation_tool_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'running', NULL, NULL)",
            (run_id, case_id, key, digest, operation, TOOL_VERSIONS[operation],
             json.dumps(parameters, sort_keys=True), started),
        )
        connection.commit()
        transaction_id = case["transaction_id"].hex()

    if after_claim is not None:
        after_claim()
    result, error, status = None, None, "succeeded"
    try:
        result = _execute(path, transaction_id, operation, parameters, scorer)
    except (ArtifactError, FileNotFoundError, sqlite3.Error):
        status, error = "unavailable", {"code": "tool_unavailable", "message": "Tool or database unavailable"}
    except ScoringDataError:
        status, error = "failed", {"code": "invalid_scoring_data", "message": "Transaction data incompatible with the model"}
    except (LookupError, ValueError):
        status, error = "failed", {"code": "tool_failed", "message": "Check could not be completed"}
    except Exception:
        status, error = "failed", {"code": "tool_failed", "message": "Check could not be completed"}

    with closing(_connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE investigation_tool_runs SET finished_at = ?, status = ?, result_json = ?, error_json = ? "
            "WHERE run_id = ? AND status = 'running'",
            (_utc(), status, json.dumps(result, ensure_ascii=False) if result is not None else None,
             json.dumps(error) if error is not None else None, run_id),
        )
        row = connection.execute(
            "SELECT * FROM investigation_tool_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        connection.commit()
        return _row(row)


def get_run(path: Path | str, case_id: str, run_id: str) -> dict[str, object]:
    with closing(_connect(path)) as connection:
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'investigation_tool_runs'"
        ).fetchone() is None:
            raise LookupError
        row = connection.execute(
            "SELECT * FROM investigation_tool_runs WHERE case_id = ? AND run_id = ?",
            (case_id, run_id),
        ).fetchone()
        if row is None:
            raise LookupError
        return _row(row)


def list_runs(path: Path | str, case_id: str, limit: int = 100) -> dict[str, object]:
    with closing(_connect(path)) as connection:
        if connection.execute(
            "SELECT 1 FROM investigation_cases WHERE case_id = ?", (case_id,)
        ).fetchone() is None:
            raise CaseNotFound
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'investigation_tool_runs'"
        ).fetchone() is None:
            return {"case_id": case_id, "limit": limit, "truncated": False, "runs": []}
        rows = connection.execute(
            "SELECT * FROM investigation_tool_runs WHERE case_id = ? "
            "ORDER BY started_at, run_id LIMIT ?", (case_id, limit + 1),
        ).fetchall()
        return {"case_id": case_id, "limit": limit, "truncated": len(rows) > limit,
                "runs": [_row(row) for row in rows[:limit]]}
