import logging
from datetime import date
from typing import Awaitable, Optional, TypeVar

from fastapi import APIRouter, Body, Depends, Path, Query, status
from portfolio_common.source_data_products import source_data_product_openapi_extra

from src.services.query_service.app.dtos.operations_dto import (
    AnalyticsExportJobListResponse,
    CalculatorSloResponse,
    FailedOutboxEventListResponse,
    FailedOutboxRequeueRequest,
    FailedOutboxRequeueResponse,
    LineageKeyListResponse,
    LineageResponse,
    LoadRunProgressResponse,
    OutboxRecoveryAuditListResponse,
    PortfolioControlStageListResponse,
    PortfolioReadinessResponse,
    ReconciliationFindingListResponse,
    ReconciliationRunListResponse,
    ReprocessingJobListResponse,
    ReprocessingKeyListResponse,
    SupportJobListResponse,
    SupportOverviewResponse,
)
from src.services.query_service.app.operations_errors import OutboxRecoveryRejected
from src.services.query_service.app.services.operations_service import OperationsService
from src.services.query_service.app.support_policy import (
    CALCULATOR_SLO_FAILED_WINDOW_DESCRIPTION,
    CALCULATOR_SLO_STALE_THRESHOLD_DESCRIPTION,
    DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
    DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    SUPPORT_FAILED_WINDOW_DESCRIPTION,
    SUPPORT_STALE_THRESHOLD_DESCRIPTION,
)

from ..dependencies import get_operations_service
from .response_helpers import problem_example, problem_response, raise_problem

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Operations Support"])

OPERATIONS_METADATA = {"route_family": "operations_support"}
PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Operations support resource not found",
    detail="Requested operations support resource was not found.",
    error_code="QCP_OPERATIONS_NOT_FOUND",
    instance="/support/portfolios/PORT-OPS-001/overview",
    metadata=OPERATIONS_METADATA,
)
INVALID_DATE_RESPONSE_DESCRIPTION = "Invalid date filter."

LINEAGE_NOT_FOUND_RESPONSE_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Operations support resource not found",
    detail="Requested operations support resource was not found.",
    error_code="QCP_OPERATIONS_NOT_FOUND",
    instance="/lineage/portfolios/PORT-OPS-001/securities/SEC-US-IBM",
    metadata={**OPERATIONS_METADATA, "resource": "lineage"},
)
RECONCILIATION_FINDINGS_NOT_FOUND_RESPONSE_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Operations support resource not found",
    detail="Requested operations support resource was not found.",
    error_code="QCP_OPERATIONS_NOT_FOUND",
    instance="/support/portfolios/PORT-OPS-001/reconciliation-runs/recon_1234567890abcdef/findings",
    metadata={**OPERATIONS_METADATA, "resource": "reconciliation_findings"},
)
OUTBOX_RECOVERY_REJECTED_RESPONSE_EXAMPLE = problem_example(
    status_code=status.HTTP_409_CONFLICT,
    title="Outbox recovery rejected",
    detail="Payload contract review confirmation is required before requeue.",
    error_code="QCP_OUTBOX_RECOVERY_REJECTED",
    instance="/support/outbox/failed-events/701/requeue",
    metadata={
        **OPERATIONS_METADATA,
        "resource": "failed_outbox_requeue",
        "outcome": "REJECTED",
    },
)
OUTBOX_RECOVERY_NOT_FOUND_RESPONSE_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Operations support resource not found",
    detail="Requested failed outbox row was not found.",
    error_code="QCP_OPERATIONS_NOT_FOUND",
    instance="/support/outbox/failed-events/701/requeue",
    metadata={**OPERATIONS_METADATA, "resource": "failed_outbox_requeue"},
)
T = TypeVar("T")


def portfolio_not_found_response(
    description: str = "Portfolio not found.",
) -> dict[str, object]:
    return problem_response(description, PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE)


def invalid_date_response(field_name: str) -> dict[str, object]:
    return problem_response(
        INVALID_DATE_RESPONSE_DESCRIPTION,
        invalid_date_response_example(field_name),
    )


def invalid_date_response_example(field_name: str) -> dict[str, object]:
    return problem_example(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Invalid operations date filter",
        detail="Invalid date filter. Expected YYYY-MM-DD format.",
        error_code="QCP_OPERATIONS_INVALID_DATE",
        instance="/support/portfolios/PORT-OPS-001/readiness",
        metadata={**OPERATIONS_METADATA, "field": field_name},
    )


def parse_optional_iso_date(field_name: str, value: Optional[str]) -> Optional[date]:
    if value is None:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        raise_problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Invalid operations date filter",
            detail="Invalid date filter. Expected YYYY-MM-DD format.",
            error_code="QCP_OPERATIONS_INVALID_DATE",
            metadata={**OPERATIONS_METADATA, "field": field_name},
        )


def parse_required_iso_date(field_name: str, value: str) -> date:
    parsed_value = parse_optional_iso_date(field_name, value)
    if parsed_value is None:
        raise_problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Missing operations date filter",
            detail="Missing required date filter.",
            error_code="QCP_OPERATIONS_MISSING_DATE",
            metadata={**OPERATIONS_METADATA, "field": field_name},
        )
    return parsed_value


async def execute_operations_call(
    operation: Awaitable[T],
    *,
    log_message: str,
    unexpected_detail: str,
    log_args: tuple[object, ...],
) -> T:
    try:
        return await operation
    except ValueError:
        raise_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Operations support resource not found",
            detail="Requested operations support resource was not found.",
            error_code="QCP_OPERATIONS_NOT_FOUND",
            metadata=OPERATIONS_METADATA,
        )
    except Exception:
        logger.exception(log_message, *log_args)
        raise_problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Operations support request failed",
            detail=unexpected_detail,
            error_code="QCP_OPERATIONS_UNEXPECTED_ERROR",
            metadata=OPERATIONS_METADATA,
        )


async def execute_outbox_recovery_call(
    operation: Awaitable[T],
    *,
    log_message: str,
    unexpected_detail: str,
    log_args: tuple[object, ...],
) -> T:
    try:
        return await operation
    except OutboxRecoveryRejected as exc:
        raise_problem(
            status_code=status.HTTP_409_CONFLICT,
            title="Outbox recovery rejected",
            detail=exc.message,
            error_code="QCP_OUTBOX_RECOVERY_REJECTED",
            metadata={
                **OPERATIONS_METADATA,
                "resource": "failed_outbox_requeue",
                **exc.metadata,
            },
        )
    except ValueError:
        raise_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Operations support resource not found",
            detail="Requested failed outbox row was not found.",
            error_code="QCP_OPERATIONS_NOT_FOUND",
            metadata={**OPERATIONS_METADATA, "resource": "failed_outbox_requeue"},
        )
    except Exception:
        logger.exception(log_message, *log_args)
        raise_problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Operations support request failed",
            detail=unexpected_detail,
            error_code="QCP_OPERATIONS_UNEXPECTED_ERROR",
            metadata={**OPERATIONS_METADATA, "resource": "failed_outbox_requeue"},
        )


@router.get(
    "/support/portfolios/{portfolio_id}/overview",
    response_model=SupportOverviewResponse,
    responses={status.HTTP_404_NOT_FOUND: portfolio_not_found_response()},
    summary="Get operational support overview for a portfolio",
    description=(
        "What: Return support-oriented operational state for one portfolio.\n"
        "How: Aggregate reprocessing, valuation, and latest-data availability markers "
        "for the key.\n"
        "When: Use in gateway support panels, operator consoles, and incident workflows to "
        "quickly assess whether portfolio processing is healthy, blocked, or backlogged. "
        "Use this route when backlog, control-stage, or replay evidence matters; use "
        "`/support/portfolios/{portfolio_id}/readiness` for source-owned readiness signals. "
        "This route publishes supportability evidence, not business-calculation inputs."
    ),
)
async def get_support_overview(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-OPS-001"],
    ),
    stale_threshold_minutes: int = Query(
        DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        ge=1,
        le=1440,
        description=SUPPORT_STALE_THRESHOLD_DESCRIPTION,
        examples=[15],
    ),
    failed_window_hours: int = Query(
        DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
        ge=1,
        le=720,
        description=SUPPORT_FAILED_WINDOW_DESCRIPTION,
        examples=[24],
    ),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_operations_call(
        service.get_support_overview(
            portfolio_id=portfolio_id,
            stale_threshold_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
        ),
        log_message="Failed to build support overview for portfolio %s",
        unexpected_detail="An unexpected server error occurred while building support overview.",
        log_args=(portfolio_id,),
    )


@router.get(
    "/support/portfolios/{portfolio_id}/readiness",
    response_model=PortfolioReadinessResponse,
    responses={
        status.HTTP_404_NOT_FOUND: portfolio_not_found_response(),
        status.HTTP_400_BAD_REQUEST: invalid_date_response("as_of_date"),
    },
    summary="Get source-owned portfolio readiness for pricing and reporting coverage",
    description=(
        "What: Return source-owned readiness states for holdings, pricing, transactions, and "
        "reporting for one portfolio.\n"
        "How: Combine durable support/control state with snapshot and historical-FX dependency "
        "signals to expose explicit readiness reasons.\n"
        "When: Use in gateway/UI and operations flows instead of inferring readiness from row "
        "counts or indirect heuristics. Use this route for front-office readiness indicators "
        "and workflow gating; use `/support/portfolios/{portfolio_id}/overview` when deeper "
        "operator backlog or incident evidence is required. This route publishes "
        "supportability and readiness posture, not calculation-grade portfolio analytics."
    ),
)
async def get_portfolio_readiness(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-OPS-001"],
    ),
    as_of_date: Optional[str] = Query(
        None,
        description=(
            "Optional as-of date in YYYY-MM-DD format used to scope booked-state readiness."
        ),
        examples=["2026-03-28"],
    ),
    stale_threshold_minutes: int = Query(
        DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        ge=1,
        le=1440,
        description=SUPPORT_STALE_THRESHOLD_DESCRIPTION,
        examples=[15],
    ),
    failed_window_hours: int = Query(
        DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
        ge=1,
        le=720,
        description=SUPPORT_FAILED_WINDOW_DESCRIPTION,
        examples=[24],
    ),
    service: OperationsService = Depends(get_operations_service),
):
    parsed_as_of_date = parse_optional_iso_date("as_of_date", as_of_date)
    return await execute_operations_call(
        service.get_portfolio_readiness(
            portfolio_id=portfolio_id,
            as_of_date=parsed_as_of_date,
            stale_threshold_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
        ),
        log_message="Failed to build readiness response for portfolio %s",
        unexpected_detail="An unexpected server error occurred while building portfolio readiness.",
        log_args=(portfolio_id,),
    )


@router.get(
    "/support/portfolios/{portfolio_id}/calculator-slos",
    response_model=CalculatorSloResponse,
    responses={status.HTTP_404_NOT_FOUND: portfolio_not_found_response()},
    summary="Get calculator SLO baseline snapshot for a portfolio",
    description=(
        "What: Return calculator backlog, stale-processing, and failed-job baselines for one "
        "portfolio.\n"
        "How: Aggregate valuation/aggregation job states and reprocessing key counts in a single "
        "support payload.\n"
        "When: Use before scaling actions, during incidents, and for daily operational SLO checks. "
        "Use this route for fleet-health baselining; drill into valuation, aggregation, replay, "
        "or export-job listings when specific stuck workloads need investigation."
    ),
)
async def get_calculator_slos(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-OPS-001"],
    ),
    stale_threshold_minutes: int = Query(
        DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        ge=1,
        le=1440,
        description=CALCULATOR_SLO_STALE_THRESHOLD_DESCRIPTION,
        examples=[15],
    ),
    failed_window_hours: int = Query(
        DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
        ge=1,
        le=720,
        description=CALCULATOR_SLO_FAILED_WINDOW_DESCRIPTION,
        examples=[24],
    ),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_operations_call(
        service.get_calculator_slos(
            portfolio_id=portfolio_id,
            stale_threshold_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
        ),
        log_message="Failed to build calculator SLO snapshot for portfolio %s",
        unexpected_detail=(
            "An unexpected server error occurred while building calculator SLO snapshot."
        ),
        log_args=(portfolio_id,),
    )


@router.get(
    "/support/load-runs/{run_id}",
    response_model=LoadRunProgressResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Load run not found.",
            problem_example(
                status_code=status.HTTP_404_NOT_FOUND,
                title="Operations support resource not found",
                detail="Requested operations support resource was not found.",
                error_code="QCP_OPERATIONS_NOT_FOUND",
                instance="/support/load-runs/20260418T065154Z",
                metadata={**OPERATIONS_METADATA, "resource": "load_run"},
            ),
        ),
        status.HTTP_400_BAD_REQUEST: invalid_date_response("business_date"),
    },
    summary="Get run-scoped load progress for institutional validation",
    description=(
        "What: Return run-scoped progress and completion telemetry for a governed load scenario.\n"
        "How: Aggregate synthetic load-run portfolio, transaction, snapshot, timeseries, and job "
        "facts using the run id naming convention and target business date.\n"
        "When: Use during institutional bank-day validation, interrupted run forensics, and "
        "operator support workflows to understand whether a load run is still seeding, "
        "materializing, complete, or failed."
    ),
)
async def get_load_run_progress(
    run_id: str = Path(
        ...,
        description="Governed load run identifier embedded in synthetic ids.",
        examples=["20260418T065154Z"],
    ),
    business_date: str = Query(
        ...,
        description=(
            "Target business date in YYYY-MM-DD format used to measure completion coverage."
        ),
        examples=["2026-04-17"],
    ),
    service: OperationsService = Depends(get_operations_service),
):
    parsed_business_date = parse_required_iso_date("business_date", business_date)
    return await execute_operations_call(
        service.get_load_run_progress(run_id=run_id, business_date=parsed_business_date),
        log_message="Failed to build load-run progress for run %s",
        unexpected_detail="An unexpected server error occurred while building load-run progress.",
        log_args=(run_id,),
    )


@router.get(
    "/support/portfolios/{portfolio_id}/control-stages",
    response_model=PortfolioControlStageListResponse,
    responses={
        status.HTTP_404_NOT_FOUND: portfolio_not_found_response(),
        status.HTTP_400_BAD_REQUEST: invalid_date_response("business_date"),
    },
    summary="List portfolio-day control stages for support workflows",
    description=(
        "What: List durable portfolio-day control stage rows for a portfolio.\n"
        "How: Query control stage records with pagination and optional stage/date/status filters.\n"
        "When: Use to inspect blocking portfolio-day controls and verify stage progression "
        "over time after `overview` or `readiness` indicates a blocked or lagging portfolio. "
        "This is operator investigation evidence, not a front-office analytics contract."
    ),
)
async def get_portfolio_control_stages(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    stage_id: Optional[int] = Query(
        None,
        description="Optional durable control-stage row id filter.",
        examples=[701],
    ),
    stage_name: Optional[str] = Query(
        None,
        description="Optional control stage filter (e.g., FINANCIAL_RECONCILIATION).",
        examples=["FINANCIAL_RECONCILIATION"],
    ),
    business_date: Optional[str] = Query(
        None,
        description="Optional business date filter in YYYY-MM-DD format.",
        examples=["2026-03-13"],
    ),
    status_filter: Optional[str] = Query(
        None,
        description=(
            "Optional control stage status filter (e.g., COMPLETED, FAILED, REQUIRES_REPLAY)."
        ),
        examples=["REQUIRES_REPLAY"],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    parsed_business_date = parse_optional_iso_date("business_date", business_date)
    return await execute_operations_call(
        service.get_portfolio_control_stages(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            stage_id=stage_id,
            stage_name=stage_name,
            business_date=parsed_business_date,
            status=status_filter,
        ),
        log_message="Failed to list portfolio control stages for portfolio %s",
        unexpected_detail=(
            "An unexpected server error occurred while listing portfolio control stages."
        ),
        log_args=(portfolio_id,),
    )


@router.get(
    "/support/portfolios/{portfolio_id}/reprocessing-keys",
    response_model=ReprocessingKeyListResponse,
    responses={
        status.HTTP_404_NOT_FOUND: portfolio_not_found_response(),
        status.HTTP_400_BAD_REQUEST: invalid_date_response("watermark_date"),
    },
    summary="List durable replay keys for support workflows",
    description=(
        "What: List durable portfolio-security replay keys for a portfolio.\n"
        "How: Query `position_state` rows with pagination and optional status, security, and "
        "watermark-date filters.\n"
        "When: Use to inspect stuck or stale REPROCESSING keys and verify replay normalization "
        "after recovery, typically after `overview` or reconciliation evidence points to replay "
        "work. These rows are operational evidence and not direct business-calculation inputs or "
        "front-office readiness indicators."
    ),
    openapi_extra=source_data_product_openapi_extra("IngestionEvidenceBundle"),
)
async def get_reprocessing_keys(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    status_filter: Optional[str] = Query(
        None,
        description="Optional replay key status filter (e.g., CURRENT, REPROCESSING).",
        examples=["REPROCESSING"],
    ),
    security_id: Optional[str] = Query(
        None,
        description="Optional security identifier filter for one replay key.",
        examples=["SEC-US-IBM"],
    ),
    watermark_date: Optional[str] = Query(
        None,
        description="Optional replay watermark date filter in YYYY-MM-DD format.",
        examples=["2026-03-10"],
    ),
    stale_threshold_minutes: int = Query(
        DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        ge=1,
        le=1440,
        description="Threshold in minutes used to classify stale support rows in this listing.",
        examples=[15],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    parsed_watermark_date = parse_optional_iso_date("watermark_date", watermark_date)
    return await execute_operations_call(
        service.get_reprocessing_keys(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            status=status_filter,
            security_id=security_id,
            watermark_date=parsed_watermark_date,
            stale_threshold_minutes=stale_threshold_minutes,
        ),
        log_message="Failed to list reprocessing keys for portfolio %s",
        unexpected_detail="An unexpected server error occurred while listing reprocessing keys.",
        log_args=(portfolio_id,),
    )


@router.get(
    "/support/portfolios/{portfolio_id}/reprocessing-jobs",
    response_model=ReprocessingJobListResponse,
    responses={status.HTTP_404_NOT_FOUND: portfolio_not_found_response()},
    summary="List durable replay jobs for support workflows",
    description=(
        "What: List durable replay jobs currently relevant to a portfolio.\n"
        "How: Query reprocessing jobs linked to the portfolio's replay keys, with pagination and "
        "optional id, status, correlation, and security filters.\n"
        "When: Use to inspect queued, stale, retried, or failed replay jobs without direct "
        "database access, typically after `overview` or reconciliation evidence indicates replay "
        "pressure. These jobs are operational evidence and not direct business-calculation inputs "
        "or front-office readiness indicators."
    ),
    openapi_extra=source_data_product_openapi_extra("IngestionEvidenceBundle"),
)
async def get_reprocessing_jobs(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    job_id: Optional[int] = Query(
        None,
        description="Optional durable replay job id filter.",
        examples=[303],
    ),
    correlation_id: Optional[str] = Query(
        None,
        description="Optional durable replay correlation identifier filter.",
        examples=["corr-replay-303"],
    ),
    status_filter: Optional[str] = Query(
        None,
        description="Optional replay job status filter (e.g., PENDING, PROCESSING, FAILED).",
        examples={"processing": {"summary": "Processing replay jobs", "value": "PROCESSING"}},
    ),
    security_id: Optional[str] = Query(
        None,
        description="Optional security identifier filter for one replay job stream.",
        examples={"security": {"summary": "Single replay security", "value": "SEC-US-IBM"}},
    ),
    stale_threshold_minutes: int = Query(
        DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        ge=1,
        le=1440,
        description="Threshold in minutes used to classify stale support rows in this listing.",
        examples=[15],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_operations_call(
        service.get_reprocessing_jobs(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            job_id=job_id,
            correlation_id=correlation_id,
            status=status_filter,
            security_id=security_id,
            stale_threshold_minutes=stale_threshold_minutes,
        ),
        log_message="Failed to list reprocessing jobs for portfolio %s",
        unexpected_detail="An unexpected server error occurred while listing reprocessing jobs.",
        log_args=(portfolio_id,),
    )


@router.get(
    "/support/portfolios/{portfolio_id}/valuation-jobs",
    response_model=SupportJobListResponse,
    responses={
        status.HTTP_404_NOT_FOUND: portfolio_not_found_response(),
        status.HTTP_400_BAD_REQUEST: invalid_date_response("business_date"),
    },
    summary="List valuation jobs for support workflows",
    description=(
        "What: List valuation jobs for a portfolio with support filters.\n"
        "How: Query valuation job records with pagination and optional id, date, security, "
        "status, and correlation filtering.\n"
        "When: Use to triage stuck valuation workloads and verify drain progress after "
        "`overview`, `calculator-slos`, or readiness evidence suggests pricing publication is "
        "lagging. This is operator support evidence, not a front-office analytics contract."
    ),
)
async def get_valuation_jobs(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    job_id: Optional[int] = Query(
        None,
        description="Optional durable valuation job id filter.",
        examples=[8801],
    ),
    security_id: Optional[str] = Query(
        None,
        description="Optional security identifier filter for one valuation job stream.",
        examples=["SEC-US-IBM"],
    ),
    business_date: Optional[str] = Query(
        None,
        description="Optional valuation business date filter in YYYY-MM-DD format.",
        examples=["2025-08-31"],
    ),
    correlation_id: Optional[str] = Query(
        None,
        description="Optional durable valuation correlation identifier filter.",
        examples=["corr-val-8801"],
    ),
    status: Optional[str] = Query(
        None,
        description="Optional job status filter (e.g., PENDING, PROCESSING).",
        examples=["PENDING"],
    ),
    stale_threshold_minutes: int = Query(
        DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        ge=1,
        le=1440,
        description="Threshold in minutes used to classify stale support rows in this listing.",
        examples=[15],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    parsed_business_date = parse_optional_iso_date("business_date", business_date)
    return await execute_operations_call(
        service.get_valuation_jobs(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            job_id=job_id,
            business_date=parsed_business_date,
            security_id=security_id,
            correlation_id=correlation_id,
            status=status,
            stale_threshold_minutes=stale_threshold_minutes,
        ),
        log_message="Failed to list valuation jobs for portfolio %s",
        unexpected_detail="An unexpected server error occurred while listing valuation jobs.",
        log_args=(portfolio_id,),
    )


@router.get(
    "/support/portfolios/{portfolio_id}/aggregation-jobs",
    response_model=SupportJobListResponse,
    responses={
        status.HTTP_404_NOT_FOUND: portfolio_not_found_response(),
        status.HTTP_400_BAD_REQUEST: invalid_date_response("business_date"),
    },
    summary="List aggregation jobs for support workflows",
    description=(
        "What: List portfolio aggregation jobs for support workflows.\n"
        "How: Query aggregation job records with pagination and optional id, date, status, "
        "and correlation filtering.\n"
        "When: Use when portfolio rollups are stale or downstream timeseries appears delayed, "
        "typically after `overview` or `calculator-slos` indicates aggregation backlog. "
        "This is operator support evidence, not a front-office analytics contract."
    ),
)
async def get_aggregation_jobs(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    job_id: Optional[int] = Query(
        None,
        description="Optional durable aggregation job id filter.",
        examples=[4402],
    ),
    correlation_id: Optional[str] = Query(
        None,
        description="Optional durable aggregation correlation identifier filter.",
        examples=["corr-agg-4402"],
    ),
    business_date: Optional[str] = Query(
        None,
        description="Optional aggregation business date filter in YYYY-MM-DD format.",
        examples=["2025-08-31"],
    ),
    status: Optional[str] = Query(
        None,
        description="Optional job status filter (e.g., PENDING, PROCESSING).",
        examples=["PENDING"],
    ),
    stale_threshold_minutes: int = Query(
        DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        ge=1,
        le=1440,
        description="Threshold in minutes used to classify stale support rows in this listing.",
        examples=[15],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    parsed_business_date = parse_optional_iso_date("business_date", business_date)
    return await execute_operations_call(
        service.get_aggregation_jobs(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            job_id=job_id,
            business_date=parsed_business_date,
            correlation_id=correlation_id,
            status=status,
            stale_threshold_minutes=stale_threshold_minutes,
        ),
        log_message="Failed to list aggregation jobs for portfolio %s",
        unexpected_detail="An unexpected server error occurred while listing aggregation jobs.",
        log_args=(portfolio_id,),
    )


@router.get(
    "/support/portfolios/{portfolio_id}/analytics-export-jobs",
    response_model=AnalyticsExportJobListResponse,
    responses={status.HTTP_404_NOT_FOUND: portfolio_not_found_response()},
    summary="List analytics export jobs for support workflows",
    description=(
        "What: List durable analytics export jobs for a portfolio with support filters.\n"
        "How: Query export job lifecycle records with pagination and optional status filtering.\n"
        "When: Use to investigate stuck, failed, or repeated analytics export requests after "
        "large-window extraction or support escalation. This is operator support evidence, not "
        "a front-office analytics contract."
    ),
)
async def get_analytics_export_jobs(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    job_id: Optional[str] = Query(
        None,
        description="Optional durable analytics export job identifier filter.",
        examples=["aexp_20260313_00012"],
    ),
    request_fingerprint: Optional[str] = Query(
        None,
        description="Optional analytics export request fingerprint filter.",
        examples=["pf-001:positions:csv"],
    ),
    status_filter: Optional[str] = Query(
        None,
        description="Optional export job status filter (e.g., accepted, running, failed).",
        examples=["failed"],
    ),
    stale_threshold_minutes: int = Query(
        DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        ge=1,
        le=1440,
        description="Threshold in minutes used to classify stale support rows in this listing.",
        examples=[15],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_operations_call(
        service.get_analytics_export_jobs(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            job_id=job_id,
            request_fingerprint=request_fingerprint,
            status=status_filter,
            stale_threshold_minutes=stale_threshold_minutes,
        ),
        log_message="Failed to list analytics export jobs for portfolio %s",
        unexpected_detail=(
            "An unexpected server error occurred while listing analytics export jobs."
        ),
        log_args=(portfolio_id,),
    )


@router.get(
    "/support/outbox/failed-events",
    response_model=FailedOutboxEventListResponse,
    summary="List failed outbox rows for operator recovery triage",
    description=(
        "What: List terminally failed outbox rows with source-safe failure metadata.\n"
        "How: Query durable `outbox_events` failure evidence with pagination and optional "
        "aggregate, topic, event-type, correlation, and reason-code filters. The raw event payload "
        "is intentionally excluded from this response.\n"
        "When: Use during event-publication incidents to identify failed rows before a governed "
        "requeue or payload-contract investigation. This is operator recovery evidence, not a "
        "business source-data or front-office analytics contract."
    ),
)
async def get_failed_outbox_events(
    aggregate_type: Optional[str] = Query(
        None,
        description="Optional outbox aggregate type filter.",
        examples=["portfolio"],
    ),
    aggregate_id: Optional[str] = Query(
        None,
        description="Optional outbox aggregate identifier filter.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    event_type: Optional[str] = Query(
        None,
        description="Optional governed event type filter.",
        examples=["PortfolioValuationCompleted"],
    ),
    topic: Optional[str] = Query(
        None,
        description="Optional Kafka topic filter.",
        examples=["portfolio.valuation.completed"],
    ),
    correlation_id: Optional[str] = Query(
        None,
        description="Optional correlation identifier filter.",
        examples=["corr-outbox-701"],
    ),
    reason_code: Optional[str] = Query(
        None,
        description="Optional source-safe failure reason code filter.",
        examples=["kafka_delivery_timeout"],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_operations_call(
        service.get_failed_outbox_events(
            skip=skip,
            limit=limit,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            topic=topic,
            correlation_id=correlation_id,
            reason_code=reason_code,
        ),
        log_message="Failed to list failed outbox rows",
        unexpected_detail="An unexpected server error occurred while listing failed outbox rows.",
        log_args=(),
    )


@router.get(
    "/support/outbox/recovery-audits",
    response_model=OutboxRecoveryAuditListResponse,
    summary="List outbox recovery audit rows for operator support",
    description=(
        "What: List durable outbox recovery audit rows with source-safe recovery metadata.\n"
        "How: Query `outbox_recovery_audit` with pagination and optional outbox row, outcome, "
        "correlation, requester, and recovery-action filters. Raw event payloads are intentionally "
        "excluded from this response.\n"
        "When: Use after failed-row diagnostics or a governed recovery command to review who "
        "requested recovery, why it was requested, whether it was accepted, and which prior "
        "failure evidence was preserved. This is operator recovery evidence, not a business "
        "source-data or front-office analytics contract."
    ),
)
async def get_outbox_recovery_audits(
    outbox_id: Optional[int] = Query(
        None,
        ge=1,
        description="Optional durable outbox row identifier filter.",
        examples=[701],
    ),
    outcome: Optional[str] = Query(
        None,
        description="Optional recovery outcome filter.",
        examples=["REQUEUED"],
    ),
    correlation_id: Optional[str] = Query(
        None,
        description="Optional incident, trace, or operator correlation identifier filter.",
        examples=["incident-20260314-outbox-701"],
    ),
    requested_by: Optional[str] = Query(
        None,
        description="Optional operator, automation principal, or support workflow filter.",
        examples=["ops.sre"],
    ),
    recovery_action: Optional[str] = Query(
        None,
        description="Optional governed recovery action filter.",
        examples=["requeue_failed_outbox"],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_operations_call(
        service.get_outbox_recovery_audits(
            skip=skip,
            limit=limit,
            outbox_id=outbox_id,
            outcome=outcome,
            correlation_id=correlation_id,
            requested_by=requested_by,
            recovery_action=recovery_action,
        ),
        log_message="Failed to list outbox recovery audit rows",
        unexpected_detail=(
            "An unexpected server error occurred while listing outbox recovery audit rows."
        ),
        log_args=(),
    )


@router.post(
    "/support/outbox/failed-events/{outbox_id}/requeue",
    response_model=FailedOutboxRequeueResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Failed outbox row was not found.",
            OUTBOX_RECOVERY_NOT_FOUND_RESPONSE_EXAMPLE,
        ),
        status.HTTP_409_CONFLICT: problem_response(
            "Outbox recovery request was rejected.",
            OUTBOX_RECOVERY_REJECTED_RESPONSE_EXAMPLE,
        ),
    },
    summary="Requeue one failed outbox row through a governed recovery workflow",
    description=(
        "What: Move one terminal failed outbox row back to pending through a controlled recovery "
        "workflow.\n"
        "How: Require operator identity, source-safe reason, optional incident correlation, and "
        "explicit payload-contract review confirmation before resetting dispatcher eligibility. "
        "The recovery audit records actor, reason, correlation, prior status, new status, and "
        "outcome evidence.\n"
        "When: Use only after failed-row diagnostics show that the publish failure is no longer "
        "active and the event payload is safe to retry. This is an operator recovery command, not "
        "a business or front-office analytics API."
    ),
)
async def requeue_failed_outbox_event(
    outbox_id: int = Path(
        ...,
        ge=1,
        description="Durable outbox row identifier to requeue.",
        examples=[701],
    ),
    request: FailedOutboxRequeueRequest = Body(
        ...,
        description="Governed failed-outbox requeue request.",
    ),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_outbox_recovery_call(
        service.requeue_failed_outbox_event(outbox_id=outbox_id, request=request),
        log_message="Failed to requeue failed outbox row %s",
        unexpected_detail="An unexpected server error occurred while requeueing failed outbox row.",
        log_args=(outbox_id,),
    )


@router.get(
    "/support/portfolios/{portfolio_id}/reconciliation-runs",
    response_model=ReconciliationRunListResponse,
    responses={status.HTTP_404_NOT_FOUND: portfolio_not_found_response()},
    summary="List reconciliation runs for support workflows",
    description=(
        "What: List durable reconciliation control runs for a portfolio.\n"
        "How: Query reconciliation run records with pagination and optional id, requester, "
        "deduplication key, type, status, and correlation filters.\n"
        "When: Use to investigate blocked portfolio-day controls, repeated replay demands, or "
        "unexpected reconciliation failures, usually after `overview` shows control blocking or "
        "`readiness` exposes unresolved source-owned gaps. These records are operator evidence, "
        "not business calculations or front-office readiness indicators."
    ),
    openapi_extra=source_data_product_openapi_extra("ReconciliationEvidenceBundle"),
)
async def get_reconciliation_runs(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    run_id: Optional[str] = Query(
        None,
        description="Optional durable reconciliation run identifier filter.",
        examples=["recon_1234567890abcdef"],
    ),
    requested_by: Optional[str] = Query(
        None,
        description="Optional reconciliation requester filter.",
        examples=["pipeline_orchestrator_service"],
    ),
    dedupe_key: Optional[str] = Query(
        None,
        description="Optional reconciliation deduplication key filter.",
        examples=["recon:transaction_cashflow:PF-001:2026-03-13:3"],
    ),
    correlation_id: Optional[str] = Query(
        None,
        description="Optional durable reconciliation correlation identifier filter.",
        examples=["corr-recon-20260313-001"],
    ),
    reconciliation_type: Optional[str] = Query(
        None,
        description="Optional reconciliation type filter (e.g., transaction_cashflow).",
        examples=["transaction_cashflow"],
    ),
    status_filter: Optional[str] = Query(
        None,
        description="Optional run status filter (e.g., COMPLETED, FAILED, REQUIRES_REPLAY).",
        examples=["FAILED"],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_operations_call(
        service.get_reconciliation_runs(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            run_id=run_id,
            requested_by=requested_by,
            dedupe_key=dedupe_key,
            correlation_id=correlation_id,
            reconciliation_type=reconciliation_type,
            status=status_filter,
        ),
        log_message="Failed to list reconciliation runs for portfolio %s",
        unexpected_detail="An unexpected server error occurred while listing reconciliation runs.",
        log_args=(portfolio_id,),
    )


@router.get(
    "/support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings",
    response_model=ReconciliationFindingListResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Portfolio or reconciliation run not found.",
            RECONCILIATION_FINDINGS_NOT_FOUND_RESPONSE_EXAMPLE,
        )
    },
    summary="List reconciliation findings for one support run",
    description=(
        "What: Return durable findings for one reconciliation run.\n"
        "How: Query persisted reconciliation findings scoped to the requested run identifier.\n"
        "When: Use after a control failure or replay requirement to inspect the exact breaches "
        "that blocked publication. These findings are operator evidence, not business "
        "calculations or front-office readiness indicators."
    ),
    openapi_extra=source_data_product_openapi_extra("ReconciliationEvidenceBundle"),
)
async def get_reconciliation_findings(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    run_id: str = Path(
        ...,
        description="Reconciliation run identifier.",
        examples=["recon_1234567890abcdef"],
    ),
    finding_id: Optional[str] = Query(
        None,
        description="Optional durable reconciliation finding identifier filter.",
        examples=["rf_1234567890abcdef"],
    ),
    security_id: Optional[str] = Query(
        None,
        description="Optional security identifier filter for reconciliation findings.",
        examples=["SEC-US-IBM"],
    ),
    transaction_id: Optional[str] = Query(
        None,
        description="Optional transaction identifier filter for reconciliation findings.",
        examples=["TXN-20260313-0042"],
    ),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum findings to return.", examples=[100]
    ),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_operations_call(
        service.get_reconciliation_findings(
            portfolio_id=portfolio_id,
            run_id=run_id,
            limit=limit,
            finding_id=finding_id,
            security_id=security_id,
            transaction_id=transaction_id,
        ),
        log_message="Failed to list reconciliation findings for portfolio %s run %s",
        unexpected_detail=(
            "An unexpected server error occurred while listing reconciliation findings."
        ),
        log_args=(portfolio_id, run_id),
    )


@router.get(
    "/lineage/portfolios/{portfolio_id}/securities/{security_id}",
    response_model=LineageResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Portfolio/security lineage not found.",
            LINEAGE_NOT_FOUND_RESPONSE_EXAMPLE,
        )
    },
    summary="Get lineage state for a portfolio-security key",
    description=(
        "What: Return lineage state for one portfolio-security key.\n"
        "How: Read epoch, watermark, and latest artifact pointers from lineage state services.\n"
        "When: Use during replay/reprocessing investigations for deterministic state validation. "
        "This is operational lineage evidence, not a business-calculation contract."
    ),
)
async def get_lineage(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    security_id: str = Path(..., description="Security identifier.", examples=["SEC-US-IBM"]),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_operations_call(
        service.get_lineage(portfolio_id, security_id),
        log_message="Failed to build lineage for portfolio %s security %s",
        unexpected_detail="An unexpected server error occurred while building lineage response.",
        log_args=(portfolio_id, security_id),
    )


@router.get(
    "/lineage/portfolios/{portfolio_id}/keys",
    response_model=LineageKeyListResponse,
    responses={status.HTTP_404_NOT_FOUND: portfolio_not_found_response()},
    summary="List lineage keys for a portfolio",
    description=(
        "What: List lineage keys for a portfolio.\n"
        "How: Query portfolio-security lineage rows with status/security filters and pagination.\n"
        "When: Use to scope impacted keys before running replay, backfill, or targeted recovery. "
        "These records are operational lineage evidence and not business-calculation inputs."
    ),
    openapi_extra=source_data_product_openapi_extra("IngestionEvidenceBundle"),
)
async def get_lineage_keys(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    reprocessing_status: Optional[str] = Query(
        None,
        description="Optional status filter for lineage keys (e.g., CURRENT, REPROCESSING).",
        examples=["CURRENT"],
    ),
    security_id: Optional[str] = Query(
        None,
        description="Optional security filter to narrow lineage key results.",
        examples=["SEC-US-IBM"],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    return await execute_operations_call(
        service.get_lineage_keys(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            reprocessing_status=reprocessing_status,
            security_id=security_id,
        ),
        log_message="Failed to list lineage keys for portfolio %s",
        unexpected_detail="An unexpected server error occurred while listing lineage keys.",
        log_args=(portfolio_id,),
    )
