import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from portfolio_common.domain.tenant import TenantContext

from ..ack_response import build_batch_ack, build_single_ack
from ..application.validate_transaction_portfolio_ownership import (
    TransactionPortfolioOwnershipRejected,
    ValidateTransactionPortfolioOwnership,
)
from ..dependencies import (
    get_ingestion_job_service,  # noqa: F401
    get_ingestion_publish_command_handler,
    get_transaction_portfolio_ownership_validator,
)
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse, IngestionAcceptedResponse
from ..DTOs.transaction_dto import Transaction, TransactionIngestionRequest
from ..ports.portfolio_tenant_ownership import PortfolioTenantOwnershipReadError
from ..request_metadata import resolve_idempotency_key
from ..services.ingestion_publish_commands import (
    BatchPublishIngestionCommand,
    IngestionPublishBookkeepingFailed,
    IngestionPublishCommandError,
    IngestionPublishCommandHandler,
    IngestionPublishUnavailable,
    SinglePublishIngestionCommand,
)
from .publish_errors import (
    ingestion_idempotency_conflict_response,
    ingestion_publish_failed_example,
    ingestion_unavailable_response,
    raise_ingestion_publish_unavailable,
)

logger = logging.getLogger(__name__)
router = APIRouter()

TRANSACTION_MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
TRANSACTION_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/transaction.",
    }
}
TRANSACTION_BATCH_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/transactions.",
    }
}
TRANSACTION_PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message="Kafka publish failed for transaction payload.",
    failed_record_keys=["TRN_001"],
)


@router.post(
    "/ingest/transaction",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionAcceptedResponse,
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the single-transaction request.",
            "content": {"application/json": {"example": TRANSACTION_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=TRANSACTION_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=TRANSACTION_PUBLISH_FAILED_EXAMPLE,
        ),
    },
    tags=["Transactions"],
    summary="Ingest a single transaction",
    description=(
        "What: Accept one canonical transaction record for ledger ingestion.\n"
        "How: Validate the portfolio against admitted tenant authority, enforce contract, "
        "mode, and rate controls, propagate any "
        "idempotency key as publish lineage, then publish asynchronously to Kafka.\n"
        "When: Use for low-volume operational corrections or single-record onboarding."
    ),
)
async def ingest_transaction(
    transaction: Transaction,
    request: Request,
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
    portfolio_ownership_validator: ValidateTransactionPortfolioOwnership = Depends(
        get_transaction_portfolio_ownership_validator
    ),
):
    idempotency_key = resolve_idempotency_key(request)
    await _validate_transaction_portfolio_ownership(
        validator=portfolio_ownership_validator,
        tenant_context=request.state.tenant_context,
        portfolio_ids=[transaction.portfolio_id],
    )
    try:
        result = await command_handler.ingest_transaction(
            SinglePublishIngestionCommand(
                tenant_context=request.state.tenant_context,
                endpoint=str(request.url.path),
                entity_type="transaction",
                record=transaction,
                idempotency_key=idempotency_key,
                accepted_message="Transaction accepted for asynchronous ingestion processing.",
            ),
        )
    except IngestionPublishCommandError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=exc.headers,
        ) from exc
    except IngestionPublishUnavailable as exc:
        raise_ingestion_publish_unavailable(exc.publish_error)

    logger.info(
        "Transaction successfully queued.", extra={"transaction_id": transaction.transaction_id}
    )
    return build_single_ack(
        message=result.message,
        entity_type=result.entity_type,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/ingest/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_idempotency_conflict_response(),
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the transaction batch request.",
            "content": {
                "application/json": {"example": TRANSACTION_BATCH_RATE_LIMIT_EXCEEDED_EXAMPLE}
            },
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=TRANSACTION_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=TRANSACTION_PUBLISH_FAILED_EXAMPLE,
        ),
    },
    tags=["Transactions"],
    summary="Ingest a transaction batch",
    description=(
        "What: Accept a batch of canonical transaction records.\n"
        "How: Validate every portfolio against admitted tenant authority, persist tenant-owned "
        "ingestion job metadata, validate payload, and publish "
        "all valid records asynchronously.\n"
        "When: Use for standard API-driven batch ingestion workflows."
    ),
)
async def ingest_transactions(
    request: TransactionIngestionRequest,
    http_request: Request,
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
    portfolio_ownership_validator: ValidateTransactionPortfolioOwnership = Depends(
        get_transaction_portfolio_ownership_validator
    ),
):
    idempotency_key = resolve_idempotency_key(http_request)
    await _validate_transaction_portfolio_ownership(
        validator=portfolio_ownership_validator,
        tenant_context=http_request.state.tenant_context,
        portfolio_ids=[transaction.portfolio_id for transaction in request.transactions],
    )
    try:
        result = await command_handler.ingest_transactions(
            BatchPublishIngestionCommand(
                tenant_context=http_request.state.tenant_context,
                endpoint=str(http_request.url.path),
                entity_type="transaction",
                records=request.transactions,
                idempotency_key=idempotency_key,
                request_payload=request.model_dump(mode="json"),
                accepted_message="Transactions accepted for asynchronous ingestion processing.",
            ),
        )
    except IngestionPublishCommandError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=exc.headers,
        ) from exc
    except IngestionPublishUnavailable as exc:
        raise_ingestion_publish_unavailable(exc.publish_error, job_id=exc.job_id)
    except IngestionPublishBookkeepingFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.detail,
        ) from exc

    if not result.replayed:
        logger.info(
            "Transactions successfully queued.",
            extra={"num_transactions": result.accepted_count},
        )
    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )


async def _validate_transaction_portfolio_ownership(
    *,
    validator: ValidateTransactionPortfolioOwnership,
    tenant_context: TenantContext,
    portfolio_ids: list[str],
) -> None:
    try:
        await validator.validate(
            tenant_context=tenant_context,
            portfolio_ids=portfolio_ids,
        )
    except TransactionPortfolioOwnershipRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INGESTION_PORTFOLIO_TENANT_MISMATCH",
                "message": (
                    "One or more transaction portfolios are outside admitted tenant authority."
                ),
                "portfolio_ids": list(exc.portfolio_ids),
            },
        ) from exc
    except PortfolioTenantOwnershipReadError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "INGESTION_PORTFOLIO_TENANT_AUTHORITY_UNAVAILABLE",
                "message": "Portfolio tenant authority could not be verified.",
            },
        ) from exc
