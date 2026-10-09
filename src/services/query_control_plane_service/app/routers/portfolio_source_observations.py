"""Single registered source-product route, separate from the zero-headroom legacy router."""

from fastapi import APIRouter, Depends, Path, Request
from portfolio_common.source_data_products import source_data_product_openapi_extra

from ..application.portfolio_source_observations import PortfolioSourceObservationsService
from ..contracts.portfolio_source_observations import (
    PortfolioSourceObservationsRequest,
    PortfolioSourceObservationsResponse,
)
from ..dependencies import get_portfolio_source_observations_service
from .response_helpers import raise_problem
from .tenant_authority import TENANT_SCOPE_FORBIDDEN_RESPONSE, require_admitted_tenant_id

router = APIRouter()


@router.post(
    "/integration/portfolios/{portfolio_id}/financial-source-observations/query",
    response_model=PortfolioSourceObservationsResponse,
    tags=["Integration"],
    summary="Read pinned portfolio financial source observations",
    description=(
        "What: read two independently attributed cash and funding/investment source families. "
        "How: require exact original pins or explicit latest-restated selection and use one "
        "tenant-scoped statement snapshot; corrections do not rewrite original pins. "
        "When: diagnostic source assembly, not cash derivation, provider qualification, joined "
        "valuation-cut coherence, eligibility or lifecycle inference. "
        "Authoritative use remains unavailable."
    ),
    responses=TENANT_SCOPE_FORBIDDEN_RESPONSE,
    openapi_extra=source_data_product_openapi_extra("PortfolioFinancialSourceObservations"),
)
async def query_portfolio_source_observations(
    request: PortfolioSourceObservationsRequest,
    http_request: Request,
    portfolio_id: str = Path(
        min_length=1, max_length=128, description="Portfolio in the admitted tenant."
    ),
    service: PortfolioSourceObservationsService = Depends(
        get_portfolio_source_observations_service
    ),
) -> PortfolioSourceObservationsResponse:
    context = http_request.state.tenant_context
    if not context.identity_verified:
        raise_problem(
            status_code=403,
            title="Tenant scope forbidden",
            detail="Verified tenant authority is required.",
            error_code="QCP_TENANT_SCOPE_FORBIDDEN",
        )
    tenant_id = require_admitted_tenant_id(request=http_request, supplied_tenant_id=None)
    return await service.query(
        tenant_id=tenant_id.value,
        portfolio_id=portfolio_id,
        request=request,
        consumer_id=context.service_identity,
    )
