"""Routes locales de suivi des enquêtes."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fraud_investigation.case_service import (
    CaseNotFound, IdempotencyConflict, TransactionNotFound,
    add_event, create_case, get_case, get_events,
)
from fraud_investigation.evidence_service import (
    RunInProgress, execute_and_record, get_run, list_runs,
)
from fraud_investigation.scoring_service import ScoreService
from fraud_investigation.report_service import (
    ReportNotFound, generate_report, get_report, list_reports,
)


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_id: str = Field(pattern=r"^[0-9a-fA-F]{32}$")


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["comment", "tool_result"]
    origin: Literal["user", "agent", "tool"]
    content: dict[str, object]
    references: list[str] = Field(default_factory=list, max_length=20)


class CaseResponse(BaseModel):
    case_id: str
    transaction_id: str
    status: Literal["open", "in_progress", "closed"]
    created_at: str
    updated_at: str


class CreatedCaseResponse(CaseResponse):
    first_event_id: str


class EventResponse(BaseModel):
    event_id: str
    case_id: str
    occurred_at: str
    event_type: str
    origin: str
    verification: Literal["verified_transaction_reference", "caller_supplied"]
    content: dict[str, object]
    references: list[str]


class EventListResponse(BaseModel):
    case_id: str
    limit: int
    truncated: bool
    events: list[EventResponse]


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["transaction", "score", "sender_history", "recipient_history"]
    limit: int | None = Field(default=None, ge=1, le=100)
    lookback_steps: int | None = Field(default=None, ge=1, le=168)

    @model_validator(mode="after")
    def history_only_parameters(self):
        if self.operation in ("transaction", "score") and (
            self.limit is not None or self.lookback_steps is not None
        ):
            raise ValueError("Les bornes ne concernent que l'historique")
        return self

    def parameters(self) -> dict[str, int]:
        if self.operation.endswith("_history"):
            return {"limit": self.limit or 50, "lookback_steps": self.lookback_steps or 168}
        return {}


class RunResponse(BaseModel):
    run_id: str
    case_id: str
    operation: str
    tool_version: str
    parameters: dict[str, int]
    started_at: str
    finished_at: str | None
    status: Literal["running", "succeeded", "unavailable", "failed"]
    result: dict[str, object] | None
    error: dict[str, object] | None
    verification: Literal["backend_executed", "pending"]
    incomplete: bool


class RunListResponse(BaseModel):
    case_id: str
    limit: int
    truncated: bool
    runs: list[RunResponse]


class ReportResponse(BaseModel):
    report_id: str
    case_id: str
    version: int
    generated_at: str
    evidence_refs: list[str]
    event_refs: list[str]
    body: dict[str, object]
    markdown: str


class ReportListResponse(BaseModel):
    case_id: str
    limit: int
    truncated: bool
    reports: list[dict[str, object]]


def case_router(database_path: Path | str,
                score_provider: Callable[[], ScoreService | None] | None = None) -> APIRouter:
    router = APIRouter()

    @router.post("/cases", status_code=201, response_model=CreatedCaseResponse)
    def new_case(request: CaseCreate,
                 idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1,
                                               max_length=128)):
        try:
            return create_case(database_path, request.transaction_id.lower(), idempotency_key)
        except TransactionNotFound:
            raise HTTPException(404, "Transaction introuvable") from None
        except IdempotencyConflict:
            raise HTTPException(409, "Clé d'idempotence déjà utilisée avec un autre contenu") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    @router.get("/cases/{case_id}", response_model=CaseResponse)
    def read_case(case_id: str):
        try:
            return get_case(database_path, case_id)
        except CaseNotFound:
            raise HTTPException(404, "Dossier introuvable") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    @router.post("/cases/{case_id}/events", status_code=201, response_model=EventResponse)
    def new_event(case_id: str, request: EventCreate,
                  idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1,
                                                max_length=128)):
        if len(request.model_dump_json()) > 16_384:
            raise HTTPException(413, "Événement trop volumineux")
        try:
            return add_event(database_path, case_id, idempotency_key,
                             request.event_type, request.origin, request.content,
                             request.references)
        except CaseNotFound:
            raise HTTPException(404, "Dossier introuvable") from None
        except IdempotencyConflict:
            raise HTTPException(409, "Clé d'idempotence déjà utilisée avec un autre contenu") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    @router.get("/cases/{case_id}/events", response_model=EventListResponse)
    def read_events(case_id: str, limit: int = Query(50, ge=1, le=100)):
        try:
            return get_events(database_path, case_id, limit)
        except CaseNotFound:
            raise HTTPException(404, "Dossier introuvable") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    @router.post("/cases/{case_id}/runs", status_code=201, response_model=RunResponse)
    def new_run(case_id: str, request: RunRequest,
                idempotency_key: str = Header(..., alias="Idempotency-Key",
                                              min_length=1, max_length=128)):
        try:
            scorer = score_provider() if score_provider else None
            return execute_and_record(database_path, case_id, idempotency_key,
                                      request.operation, request.parameters(), scorer)
        except CaseNotFound:
            raise HTTPException(404, "Dossier introuvable") from None
        except IdempotencyConflict:
            raise HTTPException(409, "Clé d'idempotence déjà utilisée avec un autre contenu") from None
        except RunInProgress:
            raise HTTPException(409, "Exécution en cours ou interrompue ; consulter les résultats") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    @router.get("/cases/{case_id}/runs", response_model=RunListResponse)
    def read_runs(case_id: str, limit: int = Query(100, ge=1, le=100)):
        try:
            return list_runs(database_path, case_id, limit)
        except CaseNotFound:
            raise HTTPException(404, "Dossier introuvable") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    @router.get("/cases/{case_id}/runs/{run_id}", response_model=RunResponse)
    def read_run(case_id: str, run_id: str):
        try:
            return get_run(database_path, case_id, run_id)
        except LookupError:
            raise HTTPException(404, "Résultat introuvable") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    @router.post("/cases/{case_id}/reports", status_code=201, response_model=ReportResponse)
    def new_report(case_id: str):
        try:
            return generate_report(database_path, case_id)
        except CaseNotFound:
            raise HTTPException(404, "Dossier introuvable") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    @router.get("/cases/{case_id}/reports", response_model=ReportListResponse)
    def read_reports(case_id: str, limit: int = Query(50, ge=1, le=100)):
        try:
            return list_reports(database_path, case_id, limit)
        except CaseNotFound:
            raise HTTPException(404, "Dossier introuvable") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    @router.get("/cases/{case_id}/reports/{version}", response_model=ReportResponse)
    def read_report(case_id: str, version: int):
        try:
            return get_report(database_path, case_id, version)
        except ReportNotFound:
            raise HTTPException(404, "Rapport introuvable") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    @router.get("/cases/{case_id}/reports/{version}/markdown", response_class=Response)
    def read_report_markdown(case_id: str, version: int):
        try:
            report = get_report(database_path, case_id, version)
            return Response(report["markdown"], media_type="text/markdown; charset=utf-8")
        except ReportNotFound:
            raise HTTPException(404, "Rapport introuvable") from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(503, "Base applicative indisponible") from None

    return router
