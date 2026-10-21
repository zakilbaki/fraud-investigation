"""API locale de consultation des transactions, indépendante du modèle ML."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from fraud_investigation.database import get_transaction, open_readonly


class TransactionResponse(BaseModel):
    transaction_id: str
    source_sha256: str
    source_line_number: int
    step: int
    type: str
    amount: str
    name_orig: str
    oldbalance_org: str
    newbalance_orig: str
    name_dest: str
    oldbalance_dest: str
    newbalance_dest: str


def create_transaction_app(database_path: Path | str = Path("data/app/fraud.sqlite")) -> FastAPI:
    """Exposer uniquement la lecture d'une transaction de la base applicative."""
    app = FastAPI(title="Fraud Investigation, consultation locale")

    @app.get("/transactions/{transaction_id}", response_model=TransactionResponse)
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
        return transaction

    return app
