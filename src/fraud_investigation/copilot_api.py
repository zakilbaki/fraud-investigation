"""Authenticated transaction lookup and frozen scoring for Copilot Studio."""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager, closing
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException

from fraud_investigation.api import ScoreRequest, ScoreResponse
from fraud_investigation.database import get_transaction, open_readonly, public_transaction
from fraud_investigation.scoring_service import (
    ArtifactError, ScoreService, ScoringDataError, ScoringPaths,
)
from fraud_investigation.transaction_api import TransactionResponse


API_KEY_ENV = "FRAUD_INVESTIGATION_API_KEY"
API_KEY_HEADER = "X-API-Key"


def create_copilot_app(
    database_path: Path | str = Path("data/app/fraud.sqlite"),
    *,
    api_key: str | None = None,
    model_path: Path | str = ScoringPaths().model,
    manifest_path: Path | str = ScoringPaths().manifest,
) -> FastAPI:
    """Expose two protected tools while keeping lookup independent of model availability."""
    configured_key = api_key if api_key is not None else os.environ.get(API_KEY_ENV)
    if not configured_key or len(configured_key) < 32 or not configured_key.strip():
        raise RuntimeError(f"{API_KEY_ENV} must contain at least 32 characters")
    expected = configured_key.encode("utf-8")

    def authenticate(supplied_key: str | None = Header(default=None, alias=API_KEY_HEADER)):
        if supplied_key is None or not secrets.compare_digest(
            supplied_key.encode("utf-8"), expected
        ):
            raise HTTPException(status_code=401, detail="API key missing or invalid")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = ScoreService(ScoringPaths(
            Path(database_path), Path(model_path), Path(manifest_path),
        ))
        app.state.scoring_available = False
        try:
            service.load()
            app.state.scoring_available = True
        except ArtifactError:
            # A missing or incompatible artifact must not disable fact lookup.
            pass
        app.state.score_service = service
        yield

    app = FastAPI(
        title="Fraud Investigation REST tools",
        lifespan=lifespan,
        dependencies=[Depends(authenticate)],
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/transactions/{transaction_id}", response_model=TransactionResponse)
    def read_transaction(transaction_id: str):
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

    @app.post("/score", response_model=ScoreResponse)
    def score_transaction(request: ScoreRequest):
        if re.fullmatch(r"[0-9a-fA-F]{32}", request.transaction_id) is None:
            raise HTTPException(
                status_code=400, detail="Invalid transaction ID: expected 32 hexadecimal characters"
            )
        if not app.state.scoring_available:
            raise HTTPException(
                status_code=503, detail="Frozen model or application database unavailable"
            )
        try:
            return app.state.score_service.score_transaction(request.transaction_id)
        except ScoringDataError:
            raise HTTPException(
                status_code=422, detail="Transaction data incompatible with the frozen pipeline"
            ) from None
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid transaction ID") from None
        except LookupError:
            raise HTTPException(status_code=404, detail="Transaction not found") from None
        except (ArtifactError, sqlite3.Error, FileNotFoundError):
            raise HTTPException(
                status_code=503, detail="Frozen model or application database unavailable"
            ) from None
        except Exception:
            raise HTTPException(status_code=500, detail="Prediction failed") from None

    return app
