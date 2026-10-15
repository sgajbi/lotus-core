"""Registered neutral flow source product and exact revision pin discovery."""

from collections.abc import Awaitable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, Path, Query, Request
from portfolio_common.domain.portfolio_source_observations import require_observation_identity
from portfolio_common.source_data_products import source_data_product_openapi_extra
from pydantic import AfterValidator

from ..application.portfolio_flow_source_observations import PortfolioFlowObservationsService
from ..contracts.portfolio_flow_source_observations import (
    FlowEventRevisionResponse,
    PortfolioFlowObservationsRequest,
    PortfolioFlowObservationsResponse,
)
from ..dependencies import get_portfolio_flow_observations_service
from .response_helpers import (
    QueryControlPlaneProblem,
    problem_example,
    problem_response,
    raise_problem,
)
from .tenant_authority import TENANT_SCOPE_FORBIDDEN_RESPONSE, require_admitted_tenant_id

router = APIRouter()
ReadResult = TypeVar("ReadResult")
FLOW_READ_RESPONSES = {
    **TENANT_SCOPE_FORBIDDEN_RESPONSE,
    404: problem_response(
        "Exact immutable flow source absent.",
        problem_example(
            status_code=404,
            title="Flow source unavailable",
            detail="The exact admitted source revision or manifest is absent.",
            error_code="QCP_FLOW_SOURCE_NOT_FOUND",
            instance="/integration/financial-source-observations/flow-events/query",
        ),
    ),
    409: problem_response(
        "Flow source or cursor did not reconcile.",
        problem_example(
            status_code=409,
            title="Flow source refused",
            detail="Source pins, complete membership, receipts or page scope did not reconcile.",
            error_code="QCP_FLOW_SOURCE_INCOMPATIBLE",
            instance="/integration/financial-source-observations/flow-events/query",
        ),
    ),
}


def _opaque_source_identity(value: str) -> str:
    require_observation_identity(value, "source identity")
    return value


def _tenant(request):
    if not request.state.tenant_context.identity_verified:
        raise_problem(
            status_code=403,
            title="Tenant scope forbidden",
            detail="Verified tenant authority is required.",
            error_code="QCP_TENANT_SCOPE_FORBIDDEN",
        )
    return require_admitted_tenant_id(request=request, supplied_tenant_id=None).value


async def _read(operation: Awaitable[ReadResult]) -> ReadResult:
    try:
        return await operation
    except LookupError:
        raise QueryControlPlaneProblem(
            status_code=404,
            title="Flow source unavailable",
            detail="The exact admitted source revision or manifest is absent.",
            error_code="QCP_FLOW_SOURCE_NOT_FOUND",
        )
    except ValueError:
        raise QueryControlPlaneProblem(
            status_code=409,
            title="Flow source refused",
            detail="Source pins, complete membership, receipts or page scope did not reconcile.",
            error_code="QCP_FLOW_SOURCE_INCOMPATIBLE",
        )


@router.post(
    "/integration/financial-source-observations/flow-events/query",
    response_model=PortfolioFlowObservationsResponse,
    tags=["Integration"],
    summary="Read an exact portfolio flow source window",
    description=(
        "What: read every producer-declared flow field and actual native receipt for an immutable "
        "source cut. How: exact cut/revision/hash, currency and complete window "
        "join pinned revisions "
        "and completed receipts in one bounded statement; signed cursors bind the "
        "full ordered set. "
        "When: unqualified source evidence for independent consumer assembly verification. UNKNOWN "
        "state or partial coverage is unavailable; explicit complete empty coverage is zero events."
    ),
    responses=FLOW_READ_RESPONSES,
    openapi_extra=source_data_product_openapi_extra("PortfolioFinancialFlowObservations"),
)
async def query_flow_source(
    request: PortfolioFlowObservationsRequest,
    http_request: Request,
    portfolio_id: Annotated[
        str,
        Query(min_length=1, max_length=128, description="Exact portfolio in the admitted tenant."),
        AfterValidator(_opaque_source_identity),
    ],
    service: PortfolioFlowObservationsService = Depends(get_portfolio_flow_observations_service),
) -> PortfolioFlowObservationsResponse:
    tenant_id = _tenant(http_request)
    return await _read(
        service.query(tenant_id=tenant_id, portfolio_id=portfolio_id, request=request)
    )


@router.get(
    "/integration/financial-source-observations/flow-events/versions/{flow_source_record_revision}",
    response_model=FlowEventRevisionResponse,
    tags=["Integration"],
    summary="Discover a retained flow event revision pin",
    description=(
        "What: obtain actual immutable observation/hash/receipt pins for a stable "
        "producer event ID. "
        "How: exact admitted tenant, portfolio, producer, event and version; no implicit latest. "
        "When: after synchronous event ingestion and before cut publication. This unqualified "
        "revision lookup does not establish complete window coverage or consumer approval."
    ),
    responses=FLOW_READ_RESPONSES,
    openapi_extra=source_data_product_openapi_extra("PortfolioFinancialFlowObservations"),
)
async def get_flow_event_revision(
    http_request: Request,
    portfolio_id: Annotated[
        str,
        Query(min_length=1, max_length=128, description="Exact portfolio in the admitted tenant."),
        AfterValidator(_opaque_source_identity),
    ],
    source_system: Annotated[
        str,
        Query(
            min_length=1,
            max_length=128,
            description="Exact admitted producer; opaque query identity.",
        ),
        AfterValidator(_opaque_source_identity),
    ],
    source_record_id: Annotated[
        str,
        Query(
            min_length=1, max_length=128, description="Stable source record; opaque query identity."
        ),
        AfterValidator(_opaque_source_identity),
    ],
    flow_source_record_revision: int = Path(
        ge=1, description="Exact original or corrected source revision."
    ),
    service: PortfolioFlowObservationsService = Depends(get_portfolio_flow_observations_service),
) -> FlowEventRevisionResponse:
    tenant_id = _tenant(http_request)
    return await _read(
        service.event(
            tenant_id=tenant_id,
            portfolio_id=portfolio_id,
            source_system=source_system,
            source_record_id=source_record_id,
            flow_source_record_revision=flow_source_record_revision,
        )
    )
