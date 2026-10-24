"""Closed, authenticated case/evidence/report interface for Copilot tools.

Authentication is supplied by the parent application. Transactions are read by
the existing services; only investigation records are written.
"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Annotated, Callable

from fastapi import APIRouter, Header, HTTPException, Path as PathParameter, Query
from pydantic import BaseModel

from fraud_investigation.case_api import (
    CaseCreate, CaseResponse, CreatedCaseResponse, ReportListResponse,
    ReportResponse, RunListResponse, RunRequest, RunResponse,
)
from fraud_investigation.case_service import (
    CaseNotFound, IdempotencyConflict, TransactionNotFound, create_case,
    find_cases_by_transaction, get_case,
)
from fraud_investigation.evidence_service import (
    RunInProgress, execute_and_record, get_run, list_runs,
)
from fraud_investigation.report_service import (
    ReportNotFound, generate_report, get_report, list_reports,
)
from fraud_investigation.scoring_service import ScoreService


Identifier = Annotated[str, PathParameter(pattern=r"^[0-9a-f]{32}$")]
RequestKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


class LatestReportReference(BaseModel):
    report_id: str
    version: int
    generated_at: str


class CaseSearchItem(CaseResponse):
    latest_report: LatestReportReference | None


class CaseSearchResponse(BaseModel):
    transaction_id: str
    limit: int
    returned_count: int
    truncated: bool
    cases: list[CaseSearchItem]


@contextmanager
def case_errors():
    try:
        yield
    except TransactionNotFound:
        raise HTTPException(404, "Transaction not found") from None
    except CaseNotFound:
        raise HTTPException(404, "Case not found") from None
    except ReportNotFound:
        raise HTTPException(404, "Report not found") from None
    except IdempotencyConflict:
        raise HTTPException(409, "Idempotency key already used with different content") from None
    except RunInProgress:
        raise HTTPException(409, "Run is in progress or interrupted; inspect recorded runs") from None
    except LookupError:
        raise HTTPException(404, "Recorded run not found") from None
    except (FileNotFoundError, sqlite3.Error):
        raise HTTPException(503, "Investigation database unavailable") from None


def copilot_case_router(database_path: Path | str,
                        score_provider: Callable[[], ScoreService | None]) -> APIRouter:
    router = APIRouter()

    @router.get("/cases", response_model=CaseSearchResponse,
                operation_id="findInvestigationCasesByTransactionId")
    def find_cases(
        transaction_id: Annotated[str, Query(pattern=r"^[0-9a-fA-F]{32}$")],
        limit: int = Query(10, ge=1, le=100),
    ):
        with case_errors():
            return find_cases_by_transaction(database_path, transaction_id, limit)

    @router.post("/cases", status_code=201, response_model=CreatedCaseResponse,
                 operation_id="createInvestigationCase")
    def new_case(request: CaseCreate, idempotency_key: RequestKey):
        with case_errors():
            return create_case(database_path, request.transaction_id.lower(), idempotency_key)

    @router.get("/cases/{case_id}", response_model=CaseResponse,
                operation_id="getInvestigationCase")
    def read_case(case_id: Identifier):
        with case_errors():
            return get_case(database_path, case_id)

    @router.post("/cases/{case_id}/runs", status_code=201, response_model=RunResponse,
                 operation_id="executeRecordedCheck")
    def new_run(case_id: Identifier, request: RunRequest, idempotency_key: RequestKey):
        with case_errors():
            return execute_and_record(database_path, case_id, idempotency_key,
                                      request.operation, request.parameters(), score_provider())

    @router.get("/cases/{case_id}/runs", response_model=RunListResponse,
                operation_id="listRecordedChecks")
    def read_runs(case_id: Identifier, limit: int = Query(50, ge=1, le=100)):
        with case_errors():
            return list_runs(database_path, case_id, limit)

    @router.get("/cases/{case_id}/runs/{run_id}", response_model=RunResponse,
                operation_id="getRecordedCheck")
    def read_run(case_id: Identifier, run_id: Identifier):
        with case_errors():
            return get_run(database_path, case_id, run_id)

    @router.post("/cases/{case_id}/reports", status_code=201, response_model=ReportResponse,
                 operation_id="generateInvestigationReport")
    def new_report(case_id: Identifier, idempotency_key: RequestKey):
        with case_errors():
            return generate_report(database_path, case_id, key=idempotency_key)

    @router.get("/cases/{case_id}/reports", response_model=ReportListResponse,
                operation_id="listInvestigationReports")
    def read_reports(case_id: Identifier, limit: int = Query(50, ge=1, le=100)):
        with case_errors():
            return list_reports(database_path, case_id, limit)

    @router.get("/cases/{case_id}/reports/{version}", response_model=ReportResponse,
                operation_id="getInvestigationReport")
    def read_report(case_id: Identifier, version: int = PathParameter(ge=1)):
        with case_errors():
            return get_report(database_path, case_id, version)

    return router
