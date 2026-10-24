"""Deterministic reports grounded in persisted backend tool results."""

from __future__ import annotations

import json
import uuid
from contextlib import closing
from pathlib import Path

from fraud_investigation.case_service import (
    MIGRATION, CaseNotFound, _cached, _connect, _digest, _event, _remember, _utc,
)
from fraud_investigation.evidence_service import RUN_INDEX, RUN_TABLE, _row


REPORT_TABLE = """
CREATE TABLE IF NOT EXISTS investigation_reports (
    report_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES investigation_cases(case_id),
    version INTEGER NOT NULL CHECK (version > 0),
    generated_at TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    event_refs_json TEXT NOT NULL,
    body_json TEXT NOT NULL,
    markdown TEXT NOT NULL,
    UNIQUE (case_id, version)
);
"""
REPORT_INDEX = """
CREATE INDEX IF NOT EXISTS investigation_reports_case_version
ON investigation_reports(case_id, version);
"""


class ReportNotFound(Exception):
    pass


def _make_body(case_id: str, transaction_id: str,
               runs: list[dict[str, object]], events: list[dict[str, object]]) -> dict[str, object]:
    checks = [{key: run[key] for key in (
        "run_id", "operation", "tool_version", "parameters", "started_at",
        "finished_at", "status", "verification", "incomplete",
    )} for run in runs]
    successful = {}
    for run in runs:
        if run["status"] == "succeeded" and run["verification"] == "backend_executed":
            successful[run["operation"]] = run

    facts = []
    provenance = None
    transaction = successful.get("transaction")
    if transaction is not None:
        result, reference = transaction["result"], transaction["run_id"]
        provenance = {"source_sha256": result["source_sha256"],
                      "source_line_number": result["source_line_number"],
                      "evidence_ref": reference}
        for name in ("transaction_id", "step", "type", "amount", "name_orig",
                     "oldbalance_org", "name_dest", "oldbalance_dest"):
            facts.append({"name": name, "value": result[name], "evidence_ref": reference})

    score_run = successful.get("score")
    score = None
    if score_run is not None:
        score = {**score_run["result"], "evidence_ref": score_run["run_id"],
                 "interpretation": (
                     "Score at or above the threshold; suspicion alert, not confirmed fraud."
                     if score_run["result"]["alert"] else
                     "Score below threshold; legitimacy is not established."
                 )}

    histories = []
    for operation in ("sender_history", "recipient_history"):
        run = successful.get(operation)
        if run is None:
            continue
        result = run["result"]
        histories.append({"operation": operation, "account_id": result["account_id"],
                          "before_step": result["before_step"],
                          "lookback_steps": result["lookback_steps"],
                          "returned_count": len(result["transactions"]),
                          "transaction_ids": [row["transaction_id"] for row in result["transactions"]],
                          "truncated": result["truncated"],
                          "evidence_ref": run["run_id"]})

    errors = [{"evidence_ref": run["run_id"], "operation": run["operation"],
               "status": run["status"], "error": run["error"]}
              for run in runs if run["status"] in ("unavailable", "failed")]
    incomplete = [{"evidence_ref": run["run_id"], "operation": run["operation"],
                   "status": run["status"]} for run in runs if run["incomplete"]]
    missing = []
    for operation, label in (("transaction", "transaction facts"),
                             ("score", "ML score"),
                             ("sender_history", "sender history"),
                             ("recipient_history", "recipient history")):
        if operation not in successful:
            missing.append(label + " unavailable or not executed")

    limits = [{"evidence_ref": h["evidence_ref"],
               "description": "History bounded to " + str(h["lookback_steps"])
               + " steps and " + str(h["returned_count"]) + " returned row(s)"
               + ("; results truncated" if h["truncated"] else "")}
              for h in histories]
    if score is not None:
        limits.append({"evidence_ref": score["evidence_ref"],
                       "description": "Suspicion score is not a calibrated probability; "
                                      "an alert is a threshold crossing, not proof of fraud"})

    comments = []
    caller_results = []
    for event in events:
        if event["verification"] != "caller_supplied":
            continue
        item = {"event_id": event["event_id"], "event_type": event["event_type"],
                "origin": event["origin"], "content": event["content"],
                "references": event["references"], "verification": "caller_supplied"}
        if event["event_type"] == "comment":
            comments.append(item)
        else:
            caller_results.append(item)

    return {"case_id": case_id, "transaction_id": transaction_id,
            "provenance": provenance, "facts": facts, "score": score,
            "histories": histories, "checks": checks, "errors": errors,
            "incomplete": incomplete, "missing": missing, "limits": limits,
            "comments": comments, "caller_submitted_results": caller_results}


def _markdown(body: dict[str, object]) -> str:
    lines = ["# Investigation report", "", f"Case: `{body['case_id']}`",
             f"Transaction: `{body['transaction_id']}`", "", "## Recorded facts"]
    if body["provenance"] is None:
        lines.append("- Provenance: unavailable in recorded results.")
    else:
        p = body["provenance"]
        lines.append(f"- Provenance: SHA-256 `{p['source_sha256']}`, source line {p['source_line_number']} "
                     f"[run `{p['evidence_ref']}`].")
    for fact in body["facts"]:
        lines.append(f"- {fact['name']} : {fact['value']} [run `{fact['evidence_ref']}`].")
    lines.extend(["", "## ML score"])
    if body["score"] is None:
        lines.append("- Score unavailable or not executed.")
    else:
        score = body["score"]
        lines.append(f"- Score {score['suspicion_score']}, threshold {score['threshold']}, "
                     f"alert {str(score['alert']).lower()} [run `{score['evidence_ref']}`].")
        lines.append(f"- Model `{score['model_version']}`, policy `{score['policy_version']}` "
                     f"[run `{score['evidence_ref']}`].")
        lines.append(f"- {score['interpretation']} [run `{score['evidence_ref']}`].")
    lines.extend(["", "## Account histories"])
    if not body["histories"]:
        lines.append("- No recorded history.")
    for history in body["histories"]:
        lines.append(f"- {history['operation']} : account `{history['account_id']}`, "
                     f"{history['returned_count']} row(s), before_step={history['before_step']}, "
                     f"lookback_steps={history['lookback_steps']}, truncated={str(history['truncated']).lower()} "
                     f"[run `{history['evidence_ref']}`].")
    lines.extend(["", "## Checks and limitations"])
    for check in body["checks"]:
        lines.append(f"- `{check['operation']}` : {check['status']} [run `{check['run_id']}`].")
    for limit in body["limits"]:
        lines.append(f"- {limit['description']} [run `{limit['evidence_ref']}`].")
    lines.extend(["", "## Errors and missing information"])
    for error in body["errors"]:
        lines.append(f"- {error['operation']} : {error['error']['message']} "
                     f"[run `{error['evidence_ref']}`].")
    for pending in body["incomplete"]:
        lines.append(f"- {pending['operation']} : run in progress or interrupted "
                     f"[run `{pending['evidence_ref']}`].")
    for missing in body["missing"]:
        lines.append(f"- {missing}.")
    lines.extend(["", "## Caller declarations, unverified"])
    for event in body["comments"] + body["caller_submitted_results"]:
        lines.append(f"- {event['event_type']} by {event['origin']} [event `{event['event_id']}`] :")
        lines.append("    " + json.dumps(event["content"], ensure_ascii=False, sort_keys=True))
    if not body["comments"] and not body["caller_submitted_results"]:
        lines.append("- No caller declarations.")
    return "\n".join(lines) + "\n"


def _report(row) -> dict[str, object]:
    return {"report_id": row["report_id"], "case_id": row["case_id"],
            "version": row["version"], "generated_at": row["generated_at"],
            "evidence_refs": json.loads(row["evidence_refs_json"]),
            "event_refs": json.loads(row["event_refs_json"]),
            "body": json.loads(row["body_json"]), "markdown": row["markdown"]}


def generate_report(path: Path | str, case_id: str, *, key: str | None = None) -> dict[str, object]:
    """Persist a snapshot; an optional retry key reuses that exact snapshot."""
    with closing(_connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        operation, digest = f"generate_report:{case_id}", _digest({"case_id": case_id})
        if key is not None:
            connection.execute(MIGRATION)
            cached = _cached(connection, operation, key, digest)
            if cached is not None:
                connection.commit()
                return cached
        connection.execute(RUN_TABLE)
        connection.execute(RUN_INDEX)
        connection.execute(REPORT_TABLE)
        connection.execute(REPORT_INDEX)
        case = connection.execute(
            "SELECT transaction_id FROM investigation_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if case is None:
            raise CaseNotFound
        runs = [_row(row) for row in connection.execute(
            "SELECT * FROM investigation_tool_runs WHERE case_id = ? "
            "ORDER BY started_at, run_id", (case_id,)
        ).fetchall()]
        events = [_event(row) for row in connection.execute(
            "SELECT * FROM investigation_events WHERE case_id = ? "
            "ORDER BY occurred_at, event_id", (case_id,)
        ).fetchall()]
        body = _make_body(case_id, case["transaction_id"].hex(), runs, events)
        version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM investigation_reports WHERE case_id = ?",
            (case_id,),
        ).fetchone()[0]
        report_id, generated_at = uuid.uuid4().hex, _utc()
        evidence_refs = [run["run_id"] for run in runs]
        event_refs = [event["event_id"] for event in events
                      if event["verification"] == "caller_supplied"]
        markdown = _markdown(body)
        connection.execute(
            "INSERT INTO investigation_reports VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (report_id, case_id, version, generated_at,
             json.dumps(evidence_refs), json.dumps(event_refs),
             json.dumps(body, ensure_ascii=False), markdown),
        )
        row = connection.execute(
            "SELECT * FROM investigation_reports WHERE report_id = ?", (report_id,)
        ).fetchone()
        result = _report(row)
        if key is not None:
            _remember(connection, operation, key, digest, result)
        connection.commit()
        return result


def get_report(path: Path | str, case_id: str, version: int) -> dict[str, object]:
    with closing(_connect(path)) as connection:
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'investigation_reports'"
        ).fetchone() is None:
            raise ReportNotFound
        row = connection.execute(
            "SELECT * FROM investigation_reports WHERE case_id = ? AND version = ?",
            (case_id, version),
        ).fetchone()
        if row is None:
            raise ReportNotFound
        return _report(row)


def list_reports(path: Path | str, case_id: str, limit: int) -> dict[str, object]:
    with closing(_connect(path)) as connection:
        if connection.execute(
            "SELECT 1 FROM investigation_cases WHERE case_id = ?", (case_id,)
        ).fetchone() is None:
            raise CaseNotFound
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'investigation_reports'"
        ).fetchone() is None:
            return {"case_id": case_id, "limit": limit, "truncated": False, "reports": []}
        rows = connection.execute(
            "SELECT * FROM investigation_reports WHERE case_id = ? "
            "ORDER BY version DESC LIMIT ?", (case_id, limit + 1),
        ).fetchall()
        return {"case_id": case_id, "limit": limit, "truncated": len(rows) > limit,
                "reports": [{"report_id": row["report_id"], "version": row["version"],
                             "generated_at": row["generated_at"],
                             "evidence_refs": json.loads(row["evidence_refs_json"])}
                            for row in rows[:limit]]}
