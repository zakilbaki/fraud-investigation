"""Bounded read-only history tools for transaction anchors or explicit accounts."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from fraud_investigation.database import (
    get_account_transactions, get_transaction, open_readonly, public_transaction,
)
from fraud_investigation.transaction_api import AccountHistoryResponse


class BoundedHistoryResponse(AccountHistoryResponse):
    min_step: int
    returned_count: int


class TransactionHistoryResponse(BoundedHistoryResponse):
    anchor_transaction_id: str
    account_role: Literal["sender", "recipient"]


def _history(connection: sqlite3.Connection, account_id: str, before_step: int,
             lookback_steps: int, limit: int) -> dict[str, object]:
    """Share exact window, truncation and public-field filtering across all tools."""
    min_step = max(1, before_step - lookback_steps)
    rows = get_account_transactions(connection, account_id, before_step, limit + 1,
                                    min_step=min_step)
    return {
        "account_id": account_id, "before_step": before_step, "min_step": min_step,
        "lookback_steps": lookback_steps, "limit": limit,
        "returned_count": min(len(rows), limit), "truncated": len(rows) > limit,
        "transactions": [public_transaction(row) for row in rows[:limit]],
    }


def history_router(database_path: Path | str) -> APIRouter:
    """Mount only on the authenticated gateway; expose no arbitrary query execution."""
    router = APIRouter()

    def anchored_history(transaction_id: str, role: Literal["sender", "recipient"],
                         lookback_steps: int, limit: int) -> dict[str, object]:
        if re.fullmatch(r"[0-9a-fA-F]{32}", transaction_id) is None:
            raise HTTPException(status_code=400,
                                detail="Invalid transaction ID: expected 32 hexadecimal characters")
        try:
            with closing(open_readonly(database_path)) as connection:
                transaction = get_transaction(connection, transaction_id)
                if transaction is None:
                    raise HTTPException(status_code=404, detail="Transaction not found")
                account_id = transaction["name_orig" if role == "sender" else "name_dest"]
                result = _history(connection, account_id, transaction["step"], lookback_steps, limit)
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(status_code=503, detail="Application database unavailable") from None
        return {**result, "anchor_transaction_id": transaction["transaction_id"],
                "account_role": role}

    @router.get("/transactions/{transaction_id}/sender-history",
                response_model=TransactionHistoryResponse)
    def sender_history(
        transaction_id: str,
        lookback_steps: int = Query(168, ge=1, le=168),
        limit: int = Query(50, ge=1, le=100),
    ):
        return anchored_history(transaction_id, "sender", lookback_steps, limit)

    @router.get("/transactions/{transaction_id}/recipient-history",
                response_model=TransactionHistoryResponse)
    def recipient_history(
        transaction_id: str,
        lookback_steps: int = Query(168, ge=1, le=168),
        limit: int = Query(50, ge=1, le=100),
    ):
        return anchored_history(transaction_id, "recipient", lookback_steps, limit)

    @router.get("/accounts/{account_id}/transactions", response_model=BoundedHistoryResponse)
    def account_history(
        account_id: str,
        before_step: int = Query(..., ge=1, le=1_000_000),
        lookback_steps: int = Query(168, ge=1, le=168),
        limit: int = Query(50, ge=1, le=100),
    ):
        if not account_id.strip() or len(account_id) > 128:
            raise HTTPException(status_code=400, detail="Invalid account identifier")
        try:
            with closing(open_readonly(database_path)) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM accounts WHERE account_id = ?", (account_id,),
                ).fetchone()
                if exists is None:
                    raise HTTPException(status_code=404, detail="Account not found")
                return _history(connection, account_id, before_step, lookback_steps, limit)
        except (FileNotFoundError, sqlite3.Error):
            raise HTTPException(status_code=503, detail="Application database unavailable") from None

    return router
