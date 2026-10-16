"""Bounded closed neutral custody collections; accepted acknowledgements earn no authority."""

from fastapi import APIRouter, Depends, HTTPException, Request
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.portfolio_financial_source_cut_admission import closed_source_json

from ..ack_response import build_batch_ack
from ..dependencies import get_portfolio_financial_source_cut_commands
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.portfolio_financial_source_cut_dto import (
    FinancialChunkInput,
    FinancialSealInput,
    RegistryChunkInput,
    RegistrySealInput,
)
from ..request_metadata import resolve_idempotency_key
from ..services.portfolio_financial_source_cut_commands import NeutralSourceSubmission

router = APIRouter(tags=["Portfolio Source Custody"])


async def submit_source(http_request, request, commands):
    key = resolve_idempotency_key(http_request)
    if key is None:
        raise HTTPException(400, detail="INGESTION_IDEMPOTENCY_KEY_REQUIRED")
    raw = await http_request.body()
    try:
        if not getattr(http_request.state, "neutral_source_closed_json", False):
            closed_source_json(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as error:
        raise HTTPException(422, detail="SOURCE_CLOSED_JSON_REQUIRED") from error
    try:
        job = await commands.submit(
            NeutralSourceSubmission(
                http_request.state.tenant_context,
                request,
                key,
                raw,
                http_request.state.neutral_source_received_at,
            )
        )
    except PermissionError as error:
        raise HTTPException(403, detail="SOURCE_REGISTRY_ADMISSION_REQUIRED") from error
    except ObservationConflict as error:
        code = str(error)
        raise HTTPException(
            {"INGESTION_MODE_BLOCKS_WRITES": 503, "INGESTION_RATE_LIMIT_EXCEEDED": 429}.get(
                code, 409
            ),
            detail=code,
        ) from error
    return build_batch_ack(
        message="Source custody command retained; poll the original native job for completion.",
        entity_type=job.entity_type,
        job_id=job.job_id,
        accepted_count=job.accepted_count,
        idempotency_key=key,
    )


@router.post(
    "/ingest/portfolio-historical-registry-chunks",
    description=(
        "What: Retain a bounded historical registry membership chunk as neutral source custody. "
        "How: Admit closed input under exact verified tenant/source grants and preserve raw and "
        "typed identity; exact replay returns the original native receipt. "
        "When: Submit chunks before their registry seal and poll the returned native job; "
        "acceptance does not qualify the source or establish bank authority."
    ),
    response_model=BatchIngestionAcceptedResponse,
    status_code=202,
)
async def ingest_registry_chunk(
    request: RegistryChunkInput,
    http_request: Request,
    commands=Depends(get_portfolio_financial_source_cut_commands),
):
    return await submit_source(http_request, request, commands)


@router.post(
    "/ingest/portfolio-historical-registry-cuts",
    description=(
        "What: Seal a declared historical registry revision, including complete-empty coverage. "
        "How: Admit closed input under exact verified tenant/source grants and compare the "
        "declared head; fenced workers reconcile retained chunks before terminal completion. "
        "When: Submit after all declared chunks and poll the original native job; "
        "custody does not verify the independent population or establish bank authority."
    ),
    response_model=BatchIngestionAcceptedResponse,
    status_code=202,
)
async def ingest_registry_cut(
    request: RegistrySealInput,
    http_request: Request,
    commands=Depends(get_portfolio_financial_source_cut_commands),
):
    return await submit_source(http_request, request, commands)


@router.post(
    "/ingest/portfolio-financial-source-cut-chunks",
    description=(
        "What: Retain a bounded chunk of selected native financial source references. "
        "How: Admit closed input under exact verified tenant/source grants and preserve raw and "
        "typed identity; exact replay returns the original native receipt. "
        "When: Submit chunks before their financial cut seal and poll the returned native job; "
        "custody performs no financial calculation or source qualification."
    ),
    response_model=BatchIngestionAcceptedResponse,
    status_code=202,
)
async def ingest_financial_chunk(
    request: FinancialChunkInput,
    http_request: Request,
    commands=Depends(get_portfolio_financial_source_cut_commands),
):
    return await submit_source(http_request, request, commands)


@router.post(
    "/ingest/portfolio-financial-source-cuts",
    description=(
        "What: Seal a declared financial source cut revision for retained consumer reads. "
        "How: Admit closed input under exact verified tenant/source grants and compare the "
        "declared head; fenced workers reconcile selections and acquire pinned native captures. "
        "When: Submit after all declared chunks and poll the original native job for completion; "
        "retained integrity does not verify cross-family compatibility or establish bank authority."
    ),
    response_model=BatchIngestionAcceptedResponse,
    status_code=202,
)
async def ingest_financial_cut(
    request: FinancialSealInput,
    http_request: Request,
    commands=Depends(get_portfolio_financial_source_cut_commands),
):
    return await submit_source(http_request, request, commands)
