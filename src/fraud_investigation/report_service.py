"""Rapports déterministes fondés sur des résultats backend conservés."""

from __future__ import annotations

import json
import uuid
from contextlib import closing
from pathlib import Path

from fraud_investigation.case_service import CaseNotFound, _connect, _event, _utc
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
                     "Score au moins égal au seuil, alerte de suspicion ; aucune fraude confirmée."
                     if score_run["result"]["alert"] else
                     "Score sous le seuil ; la légitimité n'est pas confirmée."
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
    for operation, label in (("transaction", "faits de la transaction"),
                             ("score", "score ML"),
                             ("sender_history", "historique de l'émetteur"),
                             ("recipient_history", "historique du destinataire")):
        if operation not in successful:
            missing.append(label + " indisponible ou non exécuté")

    limits = [{"evidence_ref": h["evidence_ref"],
               "description": "Historique borné à " + str(h["lookback_steps"])
               + " steps et " + str(h["returned_count"]) + " ligne(s) rendue(s)"
               + (" ; résultats tronqués" if h["truncated"] else "")}
              for h in histories]
    if score is not None:
        limits.append({"evidence_ref": score["evidence_ref"],
                       "description": "Score de suspicion non calibré comme probabilité ; "
                                      "l'alerte est un dépassement du seuil, pas une preuve de fraude"})

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
    lines = ["# Rapport d'enquête", "", f"Dossier : `{body['case_id']}`",
             f"Transaction : `{body['transaction_id']}`", "", "## Faits vérifiés"]
    if body["provenance"] is None:
        lines.append("- Provenance : non disponible dans les résultats exécutés.")
    else:
        p = body["provenance"]
        lines.append(f"- Provenance : SHA-256 `{p['source_sha256']}`, ligne {p['source_line_number']} "
                     f"[résultat `{p['evidence_ref']}`].")
    for fact in body["facts"]:
        lines.append(f"- {fact['name']} : {fact['value']} [résultat `{fact['evidence_ref']}`].")
    lines.extend(["", "## Score ML"])
    if body["score"] is None:
        lines.append("- Score indisponible ou non exécuté.")
    else:
        score = body["score"]
        lines.append(f"- Score {score['suspicion_score']}, seuil {score['threshold']}, "
                     f"alerte {str(score['alert']).lower()} [résultat `{score['evidence_ref']}`].")
        lines.append(f"- Modèle `{score['model_version']}`, politique `{score['policy_version']}` "
                     f"[résultat `{score['evidence_ref']}`].")
        lines.append(f"- {score['interpretation']} [résultat `{score['evidence_ref']}`].")
    lines.extend(["", "## Historiques"])
    if not body["histories"]:
        lines.append("- Aucun historique enregistré.")
    for history in body["histories"]:
        lines.append(f"- {history['operation']} : compte `{history['account_id']}`, "
                     f"{history['returned_count']} ligne(s), before_step={history['before_step']}, "
                     f"fenêtre={history['lookback_steps']}, troncature={str(history['truncated']).lower()} "
                     f"[résultat `{history['evidence_ref']}`].")
    lines.extend(["", "## Vérifications et limites"])
    for check in body["checks"]:
        lines.append(f"- `{check['operation']}` : {check['status']} [résultat `{check['run_id']}`].")
    for limit in body["limits"]:
        lines.append(f"- {limit['description']} [résultat `{limit['evidence_ref']}`].")
    lines.extend(["", "## Erreurs et informations manquantes"])
    for error in body["errors"]:
        lines.append(f"- {error['operation']} : {error['error']['message']} "
                     f"[résultat `{error['evidence_ref']}`].")
    for pending in body["incomplete"]:
        lines.append(f"- {pending['operation']} : exécution en cours ou interrompue "
                     f"[résultat `{pending['evidence_ref']}`].")
    for missing in body["missing"]:
        lines.append(f"- {missing}.")
    lines.extend(["", "## Déclarations de l'appelant, non vérifiées"])
    for event in body["comments"] + body["caller_submitted_results"]:
        lines.append(f"- {event['event_type']} par {event['origin']} [événement `{event['event_id']}`] :")
        lines.append("    " + json.dumps(event["content"], ensure_ascii=False, sort_keys=True))
    if not body["comments"] and not body["caller_submitted_results"]:
        lines.append("- Aucune déclaration de l'appelant.")
    return "\n".join(lines) + "\n"


def _report(row) -> dict[str, object]:
    return {"report_id": row["report_id"], "case_id": row["case_id"],
            "version": row["version"], "generated_at": row["generated_at"],
            "evidence_refs": json.loads(row["evidence_refs_json"]),
            "event_refs": json.loads(row["event_refs_json"]),
            "body": json.loads(row["body_json"]), "markdown": row["markdown"]}


def generate_report(path: Path | str, case_id: str) -> dict[str, object]:
    with closing(_connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
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
        connection.commit()
        return _report(row)


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
