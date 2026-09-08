from fastapi import APIRouter, Body, Depends, Path, Request, status
from portfolio_common.domain.tenant import TenantId
from portfolio_common.source_data_products import source_data_product_openapi_extra

from ..application.transaction_economics.service import TransactionEconomicsService
from ..contracts.performance_component_economics import (
    PERFORMANCE_COMPONENT_ECONOMICS_ROUTE_DESCRIPTION,
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
)
from ..contracts.transaction_cost_curve import (
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
)
from ..dependencies import get_transaction_economics_service
from .response_helpers import (
    problem_example,
    problem_response,
    raise_source_evidence_invalid_request,
    raise_source_evidence_not_found,
)
from .tenant_authority import (
    TENANT_SCOPE_FORBIDDEN_EXAMPLE,
    require_matching_tenant_authority,
)

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])

TRANSACTION_COST_CURVE_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Portfolio source evidence not found",
    detail="Requested portfolio source evidence was not found.",
    error_code="QCP_SOURCE_EVIDENCE_NOT_FOUND",
    metadata={
        "source_product": "TransactionCostCurve",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
    },
)
PERFORMANCE_COMPONENT_ECONOMICS_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Portfolio source evidence not found",
    detail="Requested portfolio source evidence was not found.",
    error_code="QCP_SOURCE_EVIDENCE_NOT_FOUND",
    metadata={
        "source_product": "PerformanceComponentEconomics",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
    },
)
SOURCE_EVIDENCE_INVALID_REQUEST_EXAMPLE = problem_example(
    status_code=status.HTTP_400_BAD_REQUEST,
    title="Portfolio source evidence request is invalid",
    detail="Portfolio source evidence request is invalid.",
    error_code="QCP_SOURCE_EVIDENCE_INVALID_REQUEST",
    metadata={
        "source_product": "PerformanceComponentEconomics",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
    },
)


@router.post(
    "/portfolios/{portfolio_id}/transaction-cost-curve",
    response_model=TransactionCostCurveResponse,
    summary="Resolve observed transaction-cost curve",
    description=(
        "What: Return source-owned observed transaction-cost evidence for a portfolio window.\n"
        "How: Reads booked transaction fees and fee components from lotus-core transactions, "
        "groups them by security, transaction type, and currency, and publishes observed "
        "basis-point cost points with lineage. The response is evidence from booked data, not "
        "a predictive market-impact quote or execution promise. Reads are scoped to the admitted "
        "tenant; a foreign portfolio is indistinguishable from absence.\n"
        "When: Use this endpoint when lotus-manage needs to distinguish source-backed transaction "
        "cost evidence from local estimated construction cost in DPM proof packs."
    ),
    responses={
        403: problem_response("Tenant scope forbidden", TENANT_SCOPE_FORBIDDEN_EXAMPLE),
        404: problem_response(
            "Portfolio not found",
            TRANSACTION_COST_CURVE_NOT_FOUND_EXAMPLE,
        ),
        400: problem_response(
            "Invalid transaction-cost curve request",
            problem_example(
                status_code=status.HTTP_400_BAD_REQUEST,
                title="Portfolio source evidence request is invalid",
                detail="Portfolio source evidence request is invalid.",
                error_code="QCP_SOURCE_EVIDENCE_INVALID_REQUEST",
                metadata={
                    "source_product": "TransactionCostCurve",
                    "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                },
            ),
        ),
    },
    openapi_extra=source_data_product_openapi_extra("TransactionCostCurve"),
)
async def get_transaction_cost_curve(
    http_request: Request,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose observed transaction-cost evidence is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    request: TransactionCostCurveRequest = Body(...),
    transaction_economics_service: TransactionEconomicsService = Depends(
        get_transaction_economics_service
    ),
) -> TransactionCostCurveResponse:
    admitted_tenant_id = require_matching_tenant_authority(
        supplied_tenant_id=request.tenant_id,
        tenant_context=http_request.state.tenant_context,
    )
    try:
        return await transaction_economics_service.get_transaction_cost_curve(
            portfolio_id=portfolio_id,
            tenant_id=TenantId(admitted_tenant_id),
            request=request,
        )
    except LookupError as exc:
        raise_source_evidence_not_found(
            source_product="TransactionCostCurve",
            portfolio_id=portfolio_id,
            exc=exc,
        )
    except ValueError as exc:
        raise_source_evidence_invalid_request(
            source_product="TransactionCostCurve",
            portfolio_id=portfolio_id,
            exc=exc,
        )


@router.post(
    "/portfolios/{portfolio_id}/performance-component-economics",
    response_model=PerformanceComponentEconomicsResponse,
    summary="Resolve performance component economics source evidence",
    description=PERFORMANCE_COMPONENT_ECONOMICS_ROUTE_DESCRIPTION,
    responses={
        403: problem_response("Tenant scope forbidden", TENANT_SCOPE_FORBIDDEN_EXAMPLE),
        404: problem_response(
            "Portfolio not found",
            PERFORMANCE_COMPONENT_ECONOMICS_NOT_FOUND_EXAMPLE,
        ),
        400: problem_response(
            "Invalid performance component economics request",
            SOURCE_EVIDENCE_INVALID_REQUEST_EXAMPLE,
        ),
    },
    openapi_extra=source_data_product_openapi_extra("PerformanceComponentEconomics"),
)
async def get_performance_component_economics(
    request: PerformanceComponentEconomicsRequest,
    http_request: Request,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose component economics evidence should be returned.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    transaction_economics_service: TransactionEconomicsService = Depends(
        get_transaction_economics_service
    ),
) -> PerformanceComponentEconomicsResponse:
    admitted_tenant_id = require_matching_tenant_authority(
        supplied_tenant_id=request.tenant_id,
        tenant_context=http_request.state.tenant_context,
    )
    try:
        return await transaction_economics_service.get_performance_component_economics(
            portfolio_id=portfolio_id,
            tenant_id=TenantId(admitted_tenant_id),
            request=request,
        )
    except LookupError as exc:
        raise_source_evidence_not_found(
            source_product="PerformanceComponentEconomics",
            portfolio_id=portfolio_id,
            exc=exc,
        )
    except ValueError as exc:
        raise_source_evidence_invalid_request(
            source_product="PerformanceComponentEconomics",
            portfolio_id=portfolio_id,
            exc=exc,
        )
