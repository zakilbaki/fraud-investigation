"""Routes locales de suivi des enquêtes."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fraud_investigation.case_service import (
    CaseNotFound, IdempotencyConflict, TransactionNotFound,
    add_event, create_case, get_case, get_events,
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


def case_router(database_path: Path | str) -> APIRouter:
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

    return router
