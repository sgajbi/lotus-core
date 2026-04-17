import logging
from typing import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.reference_data_dto import (
    BenchmarkCompositionIngestionRequest,
    BenchmarkDefinitionIngestionRequest,
    BenchmarkReturnSeriesIngestionRequest,
    CashAccountMasterIngestionRequest,
    ClassificationTaxonomyIngestionRequest,
    IndexDefinitionIngestionRequest,
    IndexPriceSeriesIngestionRequest,
    IndexReturnSeriesIngestionRequest,
    InstrumentLookthroughComponentIngestionRequest,
    PortfolioBenchmarkAssignmentIngestionRequest,
    RiskFreeSeriesIngestionRequest,
)
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..request_metadata import (
    create_ingestion_job_id,
    get_request_lineage,
    resolve_idempotency_key,
)
from ..services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from ..services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
    get_reference_data_ingestion_service,
)
from .job_bookkeeping import raise_post_publish_bookkeeping_failure

logger = logging.getLogger(__name__)
router = APIRouter()

REFERENCE_MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
REFERENCE_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for the requested reference-data endpoint.",
    }
}
REFERENCE_PERSIST_FAILED_EXAMPLE = {
    "detail": {
        "code": "REFERENCE_DATA_PERSIST_FAILED",
        "message": "Benchmark assignment persistence failed.",
        "job_id": "ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
    }
}


async def _handle_reference_ingestion(
    *,
    http_request: Request,
    endpoint: str,
    entity_type: str,
    accepted_count: int,
    request_payload: dict,
    persist_fn: Callable[[], Awaitable[None]],
    ingestion_job_service: IngestionJobService,
) -> BatchIngestionAcceptedResponse:
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        await ingestion_job_service.assert_ingestion_writable()
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
        ) from exc
    try:
        enforce_ingestion_write_rate_limit(endpoint=endpoint, record_count=accepted_count)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc

    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type=entity_type,
        accepted_count=accepted_count,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request_payload,
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            entity_type=entity_type,
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )

    try:
        await persist_fn()
    except Exception as exc:
        await ingestion_job_service.mark_failed(
            job_result.job.job_id,
            str(exc),
            failure_phase="persist",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "REFERENCE_DATA_PERSIST_FAILED",
                "message": str(exc),
                "job_id": job_result.job.job_id,
            },
        ) from exc

    try:
        await ingestion_job_service.mark_queued(job_result.job.job_id)
    except Exception as exc:
        await raise_post_publish_bookkeeping_failure(
            ingestion_job_service=ingestion_job_service,
            job_id=job_result.job.job_id,
            failure_reason=str(exc),
            failure_phase="persist_bookkeeping",
        )

    return build_batch_ack(
        message=f"{entity_type} accepted for asynchronous ingestion processing.",
        entity_type=entity_type,
        job_id=job_result.job.job_id,
        accepted_count=accepted_count,
        idempotency_key=idempotency_key,
    )


REFERENCE_INGESTION_RESPONSES = {
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "description": "Write-rate protection blocked the reference-data request.",
        "content": {"application/json": {"example": REFERENCE_RATE_LIMIT_EXCEEDED_EXAMPLE}},
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "description": "Reference-data persistence failed after job metadata was recorded.",
        "content": {"application/json": {"example": REFERENCE_PERSIST_FAILED_EXAMPLE}},
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "description": "Ingestion operating mode blocked writes.",
        "content": {"application/json": {"example": REFERENCE_MODE_BLOCKED_EXAMPLE}},
    },
}


@router.post(
    "/ingest/benchmark-assignments",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest portfolio benchmark assignments",
    description=(
        "What: Accept effective-dated benchmark assignment records for portfolios.\n"
        "How: Validate canonical contract, enforce ingestion controls, and "
        "upsert durable records.\n"
        "When: Use for benchmark onboarding, assignment updates, and restatement correction cycles."
    ),
)
async def ingest_benchmark_assignments(
    request: PortfolioBenchmarkAssignmentIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/benchmark-assignments",
        entity_type="benchmark_assignment",
        accepted_count=len(request.benchmark_assignments),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_portfolio_benchmark_assignments(
            [item.model_dump() for item in request.benchmark_assignments]
        ),
        ingestion_job_service=ingestion_job_service,
    )


@router.post(
    "/ingest/benchmark-definitions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest benchmark definitions",
    description=(
        "What: Accept benchmark master definition records.\n"
        "How: Validate canonical contract and upsert effective-dated benchmark metadata.\n"
        "When: Use for benchmark master onboarding and lifecycle updates."
    ),
)
async def ingest_benchmark_definitions(
    request: BenchmarkDefinitionIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/benchmark-definitions",
        entity_type="benchmark_definition",
        accepted_count=len(request.benchmark_definitions),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_benchmark_definitions(
            [item.model_dump() for item in request.benchmark_definitions]
        ),
        ingestion_job_service=ingestion_job_service,
    )


@router.post(
    "/ingest/benchmark-compositions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest benchmark composition series",
    description=(
        "What: Accept benchmark composition time-series records.\n"
        "How: Validate composition weights and upsert effective-dated component memberships.\n"
        "When: Use for benchmark rebalance and composition history maintenance."
    ),
)
async def ingest_benchmark_compositions(
    request: BenchmarkCompositionIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/benchmark-compositions",
        entity_type="benchmark_composition",
        accepted_count=len(request.benchmark_compositions),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_benchmark_compositions(
            [item.model_dump() for item in request.benchmark_compositions]
        ),
        ingestion_job_service=ingestion_job_service,
    )


@router.post(
    "/ingest/indices",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest index definitions",
    description=(
        "What: Accept index master definition records.\n"
        "How: Validate canonical contract and upsert effective-dated index metadata.\n"
        "When: Use for index onboarding and attribution metadata lifecycle updates."
    ),
)
async def ingest_indices(
    request: IndexDefinitionIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/indices",
        entity_type="index_definition",
        accepted_count=len(request.indices),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_indices(
            [item.model_dump() for item in request.indices]
        ),
        ingestion_job_service=ingestion_job_service,
    )


@router.post(
    "/ingest/index-price-series",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest index price series",
    description=(
        "What: Accept raw index price series records.\n"
        "How: Validate canonical contract and upsert time-series observations.\n"
        "When: Use for daily market close processing and historical backfills."
    ),
)
async def ingest_index_price_series(
    request: IndexPriceSeriesIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/index-price-series",
        entity_type="index_price_series",
        accepted_count=len(request.index_price_series),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_index_price_series(
            [item.model_dump() for item in request.index_price_series]
        ),
        ingestion_job_service=ingestion_job_service,
    )


@router.post(
    "/ingest/index-return-series",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest index return series",
    description=(
        "What: Accept raw vendor-provided index return series records.\n"
        "How: Validate return conventions and upsert deterministic time-series rows.\n"
        "When: Use when upstream publishes return series directly."
    ),
)
async def ingest_index_return_series(
    request: IndexReturnSeriesIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/index-return-series",
        entity_type="index_return_series",
        accepted_count=len(request.index_return_series),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_index_return_series(
            [item.model_dump() for item in request.index_return_series]
        ),
        ingestion_job_service=ingestion_job_service,
    )


@router.post(
    "/ingest/benchmark-return-series",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest benchmark return series",
    description=(
        "What: Accept raw vendor-provided benchmark return series records.\n"
        "How: Validate return conventions and upsert deterministic time-series rows.\n"
        "When: Use when benchmark return series is provided by upstream vendor."
    ),
)
async def ingest_benchmark_return_series(
    request: BenchmarkReturnSeriesIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/benchmark-return-series",
        entity_type="benchmark_return_series",
        accepted_count=len(request.benchmark_return_series),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_benchmark_return_series(
            [item.model_dump() for item in request.benchmark_return_series]
        ),
        ingestion_job_service=ingestion_job_service,
    )


@router.post(
    "/ingest/risk-free-series",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest risk-free series",
    description=(
        "What: Accept risk-free reference series records.\n"
        "How: Validate convention fields and upsert deterministic time-series rows.\n"
        "When: Use for benchmark-relative analytics and risk-adjusted metric inputs."
    ),
)
async def ingest_risk_free_series(
    request: RiskFreeSeriesIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/risk-free-series",
        entity_type="risk_free_series",
        accepted_count=len(request.risk_free_series),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_risk_free_series(
            [item.model_dump() for item in request.risk_free_series]
        ),
        ingestion_job_service=ingestion_job_service,
    )


@router.post(
    "/ingest/reference/classification-taxonomy",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest classification taxonomy",
    description=(
        "What: Accept classification taxonomy records used for attribution alignment.\n"
        "How: Validate canonical dimensions and upsert effective-dated taxonomy entries.\n"
        "When: Use when platform taxonomy labels are introduced or updated."
    ),
)
async def ingest_classification_taxonomy(
    request: ClassificationTaxonomyIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/reference/classification-taxonomy",
        entity_type="classification_taxonomy",
        accepted_count=len(request.classification_taxonomy),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_classification_taxonomy(
            [item.model_dump() for item in request.classification_taxonomy]
        ),
        ingestion_job_service=ingestion_job_service,
    )


@router.post(
    "/ingest/reference/cash-accounts",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest cash-account master records",
    description=(
        "What: Accept canonical cash-account master records.\n"
        "How: Validate PB/WM cash-account identity and upsert durable portfolio/account linkage "
        "metadata.\n"
        "When: Use during onboarding and cash-account lifecycle maintenance."
    ),
)
async def ingest_cash_account_masters(
    request: CashAccountMasterIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/reference/cash-accounts",
        entity_type="cash_account_master",
        accepted_count=len(request.cash_accounts),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_cash_account_masters(
            [item.model_dump() for item in request.cash_accounts]
        ),
        ingestion_job_service=ingestion_job_service,
    )


@router.post(
    "/ingest/reference/instrument-lookthrough-components",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses=REFERENCE_INGESTION_RESPONSES,
    tags=["Reference Data"],
    summary="Ingest instrument look-through components",
    description=(
        "What: Accept effective-dated look-through composition rows for funds and structured "
        "products.\n"
        "How: Validate component weights and upsert durable decomposition records.\n"
        "When: Use when downstream allocation consumers need source-owned look-through views."
    ),
)
async def ingest_instrument_lookthrough_components(
    request: InstrumentLookthroughComponentIngestionRequest,
    http_request: Request,
    reference_data_service: ReferenceDataIngestionService = Depends(
        get_reference_data_ingestion_service
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> BatchIngestionAcceptedResponse:
    return await _handle_reference_ingestion(
        http_request=http_request,
        endpoint="/ingest/reference/instrument-lookthrough-components",
        entity_type="instrument_lookthrough_component",
        accepted_count=len(request.lookthrough_components),
        request_payload=request.model_dump(mode="json"),
        persist_fn=lambda: reference_data_service.upsert_instrument_lookthrough_components(
            [item.model_dump() for item in request.lookthrough_components]
        ),
        ingestion_job_service=ingestion_job_service,
    )
