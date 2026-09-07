"""HTTP boundary for tenant-authoritative benchmark assignment resolution."""

from fastapi import APIRouter, Depends, Path, Request, status
from portfolio_common.source_data_products import source_data_product_openapi_extra

from ..application.benchmark_assignment import BenchmarkAssignmentService
from ..contracts.benchmark_assignment import (
    BenchmarkAssignmentRequest,
    BenchmarkAssignmentResponse,
)
from ..dependencies import get_benchmark_assignment_service
from .response_helpers import problem_example, problem_response, raise_problem
from .tenant_authority import (
    TENANT_SCOPE_FORBIDDEN_EXAMPLE,
    require_matching_tenant_authority,
)

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])

NOT_FOUND_DETAIL = "No effective benchmark assignment found for portfolio and as_of_date."
NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Integration source data not found",
    detail=NOT_FOUND_DETAIL,
    error_code="QCP_INTEGRATION_SOURCE_NOT_FOUND",
    instance="/integration/portfolios/PORT-INT-001/benchmark-assignment",
    metadata={
        "source_product": "BenchmarkAssignment",
        "portfolio_id": "PORT-INT-001",
        "reason": "not_found",
    },
)


@router.post(
    "/portfolios/{portfolio_id}/benchmark-assignment",
    response_model=BenchmarkAssignmentResponse,
    responses={
        status.HTTP_403_FORBIDDEN: problem_response(
            "Requested tenant does not match admitted tenant authority.",
            TENANT_SCOPE_FORBIDDEN_EXAMPLE,
        ),
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective benchmark assignment found.",
            NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve effective portfolio benchmark assignment",
    description=(
        "What: Resolve benchmark assignment for a portfolio as-of a point-in-time date.\n"
        "How: Applies effective-dating and assignment version ordering to return "
        "deterministic match within the admitted tenant. An optional policy_context tenant "
        "is an assertion that must match admitted authority; reporting_currency and policy "
        "pack context do not change assignment selection. Foreign portfolios are returned "
        "as not found.\n"
        "When: Used by lotus-performance benchmark-aware analytics, lotus-gateway workspace "
        "composition flows, and reporting workflows that need governed benchmark context "
        "before downstream benchmark math or evidence generation."
    ),
    openapi_extra=source_data_product_openapi_extra("BenchmarkAssignment"),
)
async def resolve_portfolio_benchmark_assignment(
    request: BenchmarkAssignmentRequest,
    http_request: Request,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose effective benchmark assignment is requested.",
        examples=["PORT-INT-001"],
    ),
    benchmark_assignment_service: BenchmarkAssignmentService = Depends(
        get_benchmark_assignment_service
    ),
) -> BenchmarkAssignmentResponse:
    supplied_tenant_id = (
        request.policy_context.tenant_id
        if request.policy_context is not None and request.policy_context.tenant_id is not None
        else str(http_request.state.tenant_context.tenant_id)
    )
    admitted_tenant_id = require_matching_tenant_authority(
        supplied_tenant_id=supplied_tenant_id,
        tenant_context=http_request.state.tenant_context,
    )
    response = await benchmark_assignment_service.resolve(
        portfolio_id=portfolio_id,
        tenant_id=admitted_tenant_id,
        request=request,
    )
    if response is None:
        raise_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Integration source data not found",
            detail=NOT_FOUND_DETAIL,
            error_code="QCP_INTEGRATION_SOURCE_NOT_FOUND",
            metadata={
                "source_product": "BenchmarkAssignment",
                "portfolio_id": portfolio_id,
                "reason": "not_found",
            },
        )
    return response
