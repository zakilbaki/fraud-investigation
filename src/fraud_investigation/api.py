"""API locale de lecture et scoring des transactions PaySim déjà importées."""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from fraud_investigation.scoring_service import (
    ArtifactError, ScoreService, ScoringDataError, ScoringPaths,
)


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_id: str


def create_app(paths: ScoringPaths | None = None) -> FastAPI:
    configured = paths or ScoringPaths()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = ScoreService(configured)
        try:
            service.load()
            app.state.load_error = None
        except ArtifactError as exc:
            app.state.load_error = str(exc)
        app.state.service = service
        yield

    app = FastAPI(title="Fraud Investigation, API locale", lifespan=lifespan)

    @app.get("/health")
    def health():
        service = app.state.service
        if app.state.load_error:
            raise HTTPException(status_code=503, detail=app.state.load_error)
        return {"status": "ready", "model_available": True,
                "model_version": service.model_version}

    @app.post("/score")
    def score(request: ScoreRequest):
        if app.state.load_error:
            raise HTTPException(status_code=503, detail=app.state.load_error)
        try:
            return app.state.service.score_transaction(request.transaction_id)
        except ValueError as exc:
            if isinstance(exc, ScoringDataError):
                raise HTTPException(status_code=422, detail=str(exc)) from None
            raise HTTPException(status_code=400, detail="Identifiant de transaction invalide") from None
        except LookupError:
            raise HTTPException(status_code=404, detail="Transaction introuvable") from None
        except (ArtifactError, sqlite3.Error, FileNotFoundError):
            raise HTTPException(status_code=503, detail="Modèle ou base indisponible") from None
        except Exception:
            raise HTTPException(status_code=500, detail="Erreur de prédiction") from None

    return app
