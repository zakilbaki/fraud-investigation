"""Scoring local d'une transaction déjà présente dans la base applicative."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from fraud_investigation.database import (
    count_prior_receipts, get_scoring_transaction, open_readonly,
)
from fraud_investigation.ml_benchmark import TYPES, scores
from fraud_investigation.ml_final import MODEL_COLUMNS, sha256

POLICY_VERSION = "final_global_f1_v1"
FINAL_THRESHOLD = 0.3123179923852385


class ArtifactError(RuntimeError):
    """Modèle, manifeste ou base absents ou incompatibles."""


class ScoringDataError(ValueError):
    """Ligne applicative impossible à transformer comme lors de l'évaluation."""


@dataclass(frozen=True)
class ScoringPaths:
    database: Path = Path("data/app/fraud.sqlite")
    model: Path = Path("data/ml_final_catboost/pipeline.joblib")
    manifest: Path = Path("docs/results/ml_final_manifest.json")


class ScoreService:
    def __init__(self, paths: ScoringPaths):
        self.paths = paths
        self.features = None
        self.model = None
        self.manifest = None
        self.threshold = None
        self.model_version = None

    def load(self) -> None:
        """Charger une seule fois, sans entraînement ni fichier d'évaluation."""
        try:
            if not self.paths.manifest.is_file():
                raise ArtifactError("Manifeste du modèle absent")
            if not self.paths.model.is_file():
                raise ArtifactError("Modèle local absent")
            if not self.paths.database.is_file():
                raise ArtifactError("Base applicative absente")
            manifest = json.loads(self.paths.manifest.read_text())
            if sha256(self.paths.model) != manifest["pipeline_sha256"]:
                raise ArtifactError("Empreinte du modèle incompatible avec le manifeste")
            if manifest["model_config"] != "cat_slow200" or manifest["threshold"] != FINAL_THRESHOLD:
                raise ArtifactError("Politique finale incompatible")
            if manifest["predictor_columns"] != list(MODEL_COLUMNS):
                raise ArtifactError("Colonnes du modèle incompatibles")
            frozen = joblib.load(self.paths.model)
            if (frozen["threshold"] != FINAL_THRESHOLD
                    or frozen["features"].columns != list(MODEL_COLUMNS)
                    or frozen["model"].get_params() != manifest["model_parameters"]):
                raise ArtifactError("Pipeline incompatible avec le manifeste")
            with closing(open_readonly(self.paths.database)) as connection:
                connection.execute("PRAGMA query_only = ON")
                row = connection.execute(
                    "SELECT source_sha256 FROM transactions ORDER BY source_line_number LIMIT 1"
                ).fetchone()
                if row is None or row[0] != bytes.fromhex(manifest["csv_sha256"]):
                    raise ArtifactError("Base applicative incompatible avec la source du modèle")
            self.features, self.model = frozen["features"], frozen["model"]
            self.manifest, self.threshold = manifest, FINAL_THRESHOLD
            self.model_version = f"{manifest['model_config']}:{manifest['pipeline_sha256'][:12]}"
        except ArtifactError:
            raise
        except Exception as exc:
            raise ArtifactError("Artefact ou base absent ou incompatible") from exc

    def score_transaction(self, transaction_id: str) -> dict[str, object]:
        result, _ = self.score_transaction_measured(transaction_id)
        return result

    def score_transaction_measured(self, transaction_id: str) -> tuple[dict[str, object], dict[str, float]]:
        """Mesures locales détaillées, exclues de la réponse publique."""
        if self.model is None or self.features is None or self.manifest is None:
            raise ArtifactError("Modèle indisponible")
        start = time.perf_counter()
        with closing(open_readonly(self.paths.database)) as connection:
            connection.execute("PRAGMA query_only = ON")
            row = get_scoring_transaction(connection, transaction_id)
            if row is None:
                raise LookupError("Transaction introuvable")
            if row["source_sha256"] != bytes.fromhex(self.manifest["csv_sha256"]):
                raise ScoringDataError("Provenance de la transaction incompatible")
            prior = count_prior_receipts(connection, row["name_dest"], row["step"])
        after_read = time.perf_counter()
        try:
            step = int(row["step"])
            if not 1 <= step <= np.iinfo(np.int16).max or row["type"] not in TYPES:
                raise ValueError("Step ou type invalide")
            amount = np.asarray([float(row["amount"])], dtype=np.float32)
            balance = np.asarray([float(row["oldbalance_org"])], dtype=np.float32)
            if not (np.isfinite(amount).all() and np.isfinite(balance).all()
                    and (amount >= 0).all() and (balance >= 0).all()):
                raise ValueError("Montant ou solde invalide")
            kind = np.asarray([TYPES.index(row["type"])], dtype=np.uint8)
            count = np.asarray([prior], dtype=np.float32)
            if not np.isfinite(count).all():
                raise ValueError("Compteur hors plage numérique")
            x = self.features.transform(kind, amount, balance,
                                        np.asarray([step], dtype=np.int16), count)
            if list(x.columns) != list(MODEL_COLUMNS):
                raise ValueError("Colonnes de prédiction incompatibles")
        except (ValueError, TypeError, AssertionError, OverflowError) as exc:
            raise ScoringDataError("Données incompatibles avec le pipeline") from exc
        after_features = time.perf_counter()
        try:
            score = float(scores(self.model, x)[0])
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Score non fini ou hors plage")
        except (ValueError, TypeError, AssertionError) as exc:
            raise ScoringDataError("Prédiction impossible pour cette transaction") from exc
        after_score = time.perf_counter()
        return ({"transaction_id": row["transaction_id"].hex(),
                 "suspicion_score": score, "threshold": self.threshold,
                 "alert": score >= self.threshold, "model_version": self.model_version,
                 "policy_version": POLICY_VERSION},
                {"read_and_history_ms": (after_read-start)*1000,
                 "features_ms": (after_features-after_read)*1000,
                 "prediction_ms": (after_score-after_features)*1000})
