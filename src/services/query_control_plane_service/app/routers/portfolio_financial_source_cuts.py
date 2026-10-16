"""Registered exact neutral read collections with independent consumer authorization."""

from typing import NoReturn, TypeVar, cast

from fastapi import APIRouter, Depends, Request
from portfolio_common.enterprise_readiness import VerifiedServicePrincipal, verify_service_principal
from portfolio_common.source_data_products import (
    get_source_data_product,
    source_data_product_openapi_extra,
)
from portfolio_common.source_data_security import (
    NEUTRAL_SOURCE_READ_FEATURES,
    require_neutral_source_read_grant,
    required_source_data_capability,
)

from ..application.capabilities_service import CapabilitiesService
from ..application.portfolio_financial_source_cuts import PortfolioFinancialSourceCutsService
from ..contracts.portfolio_financial_source_cuts import (
    FinancialSourceCutQuery,
    FinancialSourceCutReadResponse,
    HistoricalRegistryQuery,
    HistoricalRegistryReadResponse,
    SourceCutReadResponse,
)
from ..dependencies import (
    get_neutral_source_read_grants,
    get_portfolio_financial_source_cuts_service,
)
from ..settings import load_query_control_plane_settings
from .response_helpers import QueryControlPlaneProblem, problem_example, problem_response

router = APIRouter(tags=["Integration"])
ReadResponse = TypeVar("ReadResponse", bound=SourceCutReadResponse)
READ_RESPONSES = {
    status: problem_response(
        detail,
        problem_example(
            status_code=status,
            title="Source custody read refused",
            detail=detail,
            error_code=code,
            instance="/integration/financial-source-cuts/query",
        ),
    )
    for status, code, detail in (
        (
            403,
            "QCP_SOURCE_CUT_SCOPE_FORBIDDEN",
            "Verified service, tenant, product and registry read authority is required.",
        ),
        (
            404,
            "QCP_SOURCE_CUT_NOT_FOUND",
            "The exact retained source cut or selected input is absent.",
        ),
        (
            409,
            "QCP_SOURCE_CUT_INCOMPATIBLE",
            "Retained receipt, source roots, capture catalog or continuation did not reconcile.",
        ),
        (503, "QCP_SOURCE_CUT_UNAVAILABLE", "The retained source read capability is unavailable."),
    )
}


def refuse(status: int) -> NoReturn:
    detail = READ_RESPONSES[status]["content"]["application/problem+json"]["example"]
    raise QueryControlPlaneProblem(
        status_code=status,
        title=detail["title"],
        detail=detail["detail"],
        error_code=detail["error_code"],
    )


async def read_source_cut(
    request, http_request, service, grants, product, response_type: type[ReadResponse]
) -> ReadResponse:
    context = getattr(http_request.state, "tenant_context", None)
    principal = verify_service_principal(
        dict(http_request.headers), load_query_control_plane_settings()
    )
    if (
        not isinstance(principal, VerifiedServicePrincipal)
        or context is None
        or not context.identity_verified
        or principal.service_identity != context.service_identity
        or required_source_data_capability(product) not in principal.capabilities
        or principal.service_identity not in get_source_data_product(product).consumers
    ):
        refuse(403)
    try:
        require_neutral_source_read_grant(
            grants,
            tenant_id=context.tenant_id_text,
            service_identity=principal.service_identity,
            product=product,
            source_system=request.source_system,
            registry_scope_id=request.registry_scope_id,
        )
    except (PermissionError, ValueError):
        refuse(403)
    capabilities = CapabilitiesService().get_integration_capabilities(
        consumer_system=principal.service_identity, tenant_id=context.tenant_id_text
    )
    enabled = {feature.key: feature.enabled for feature in capabilities.features}
    if not enabled.get(NEUTRAL_SOURCE_READ_FEATURES[product], False):
        refuse(503)
    try:
        response = await service.query(
            tenant_id=context.tenant_id_text,
            service_identity=principal.service_identity,
            product=product,
            request=request,
        )
        return cast(ReadResponse, response_type.model_validate(response, from_attributes=True))
    except LookupError:
        refuse(404)
    except (ValueError, KeyError, TypeError):
        refuse(409)


@router.post(
    "/integration/portfolio-historical-registries/query",
    response_model=HistoricalRegistryReadResponse,
    summary="Read an exact retained historical registry",
    description=(
        "Read a batch manifest, all declared members, or retained ingress capture segments by "
        "exact source address and bare batch root. Verified service and tenant authority, a "
        "registry product grant and enabled capability are required. Signed keyset pages bound "
        "rows and bytes; completion remains unqualified and population unverified."
    ),
    responses=READ_RESPONSES,
    openapi_extra=source_data_product_openapi_extra("PortfolioHistoricalRegistry"),
)
async def query_historical_registry(
    request: HistoricalRegistryQuery,
    http_request: Request,
    service: PortfolioFinancialSourceCutsService = Depends(
        get_portfolio_financial_source_cuts_service
    ),
    grants=Depends(get_neutral_source_read_grants),
) -> HistoricalRegistryReadResponse:
    return await read_source_cut(
        request,
        http_request,
        service,
        grants,
        "PortfolioHistoricalRegistry",
        HistoricalRegistryReadResponse,
    )


@router.post(
    "/integration/financial-source-cuts/query",
    response_model=FinancialSourceCutReadResponse,
    summary="Read an exact retained financial source cut",
    description=(
        "Read the batch manifest, independent selected five-role declaration and graph, or "
        "retained native capture segments for the opaque portfolio in the body. The batch root "
        "is distinct from the selected graph and artifact roots. Native serializer recipes must "
        "be admitted before capture decoding; custody does not establish financial, supplier "
        "or bank authority."
    ),
    responses=READ_RESPONSES,
    openapi_extra=source_data_product_openapi_extra("PortfolioFinancialSourceCut"),
)
async def query_financial_source_cut(
    request: FinancialSourceCutQuery,
    http_request: Request,
    service: PortfolioFinancialSourceCutsService = Depends(
        get_portfolio_financial_source_cuts_service
    ),
    grants=Depends(get_neutral_source_read_grants),
) -> FinancialSourceCutReadResponse:
    return await read_source_cut(
        request,
        http_request,
        service,
        grants,
        "PortfolioFinancialSourceCut",
        FinancialSourceCutReadResponse,
    )
