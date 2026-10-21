"""API locale de consultation des transactions, indépendante du modèle ML."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import BaseModel

from fraud_investigation.database import (
    get_account_transactions, get_transaction, open_readonly, public_transaction,
)
from fraud_investigation.case_api import case_router


class TransactionResponse(BaseModel):
    transaction_id: str
    source_sha256: str
    source_line_number: int
    step: int
    type: str
    amount: str
    name_orig: str
    oldbalance_org: str
    name_dest: str
    oldbalance_dest: str


class AccountHistoryResponse(BaseModel):
    account_id: str
    before_step: int
    lookback_steps: int
    limit: int
    truncated: bool
    transactions: list[TransactionResponse]


def transaction_router(database_path: Path | str) -> APIRouter:
    router = APIRouter()

    @router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
    def read_transaction(transaction_id: str) -> dict[str, object]:
        try:
            with closing(open_readonly(database_path)) as connection:
                transaction = get_transaction(connection, transaction_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Identifiant invalide : 32 caractères hexadécimaux requis"
            ) from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(status_code=503, detail="Base applicative indisponible") from None

        if transaction is None:
            raise HTTPException(status_code=404, detail="Transaction introuvable")
        return public_transaction(transaction)

    @router.get("/accounts/{account_id}/transactions", response_model=AccountHistoryResponse)
    def read_account_history(
        account_id: str,
        before_step: int = Query(..., ge=1, le=1_000_000),
        lookback_steps: int = Query(168, ge=1, le=168),
        limit: int = Query(50, ge=1, le=100),
    ) -> dict[str, object]:
        if not account_id.strip() or len(account_id) > 128:
            raise HTTPException(status_code=400, detail="Identifiant de compte invalide")
        try:
            with closing(open_readonly(database_path)) as connection:
                rows = get_account_transactions(
                    connection, account_id, before_step, limit + 1,
                    min_step=max(1, before_step - lookback_steps),
                )
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(status_code=503, detail="Base applicative indisponible") from None
        return {
            "account_id": account_id,
            "before_step": before_step,
            "lookback_steps": lookback_steps,
            "limit": limit,
            "truncated": len(rows) > limit,
            "transactions": [public_transaction(row) for row in rows[:limit]],
        }

    return router


def create_transaction_app(database_path: Path | str = Path("data/app/fraud.sqlite")) -> FastAPI:
    """Exposer la consultation sans charger le modèle ML."""
    app = FastAPI(title="Fraud Investigation, consultation locale")
    app.include_router(transaction_router(database_path))
    app.include_router(case_router(database_path))
    return app
