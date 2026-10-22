"""Surface REST minimale destinée à une future connexion Copilot Studio."""

from __future__ import annotations

import os
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException

from fraud_investigation.database import get_transaction, open_readonly, public_transaction
from fraud_investigation.transaction_api import TransactionResponse


API_KEY_ENV = "FRAUD_INVESTIGATION_API_KEY"
API_KEY_HEADER = "X-API-Key"


def create_copilot_app(
    database_path: Path | str = Path("data/app/fraud.sqlite"),
    *,
    api_key: str | None = None,
) -> FastAPI:
    """N'exposer qu'une recherche protégée ; refuser un secret absent ou faible."""
    configured_key = api_key if api_key is not None else os.environ.get(API_KEY_ENV)
    if not configured_key or len(configured_key) < 32 or not configured_key.strip():
        raise RuntimeError(f"{API_KEY_ENV} doit contenir au moins 32 caractères")
    expected = configured_key.encode("utf-8")
    app = FastAPI(
        title="Fraud Investigation, connexion REST",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/transactions/{transaction_id}", response_model=TransactionResponse)
    def read_transaction(transaction_id: str,
                         supplied_key: str | None = Header(default=None, alias=API_KEY_HEADER)):
        if supplied_key is None or not secrets.compare_digest(
            supplied_key.encode("utf-8"), expected
        ):
            raise HTTPException(status_code=401, detail="API key missing or invalid")
        try:
            with closing(open_readonly(database_path)) as connection:
                transaction = get_transaction(connection, transaction_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid transaction ID: expected 32 hexadecimal characters"
            ) from None
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(status_code=503, detail="Application database unavailable") from None
        if transaction is None:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return public_transaction(transaction)

    return app
