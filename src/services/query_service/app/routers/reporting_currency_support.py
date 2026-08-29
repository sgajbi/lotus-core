from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..application.reporting_currency_support import ReportingCurrencySupportQuery
from ..dependencies import get_reporting_currency_support_service
from ..dtos.reporting_currency_support_dto import ReportingCurrencySupportResponse
from ..services.reporting_currency_support_service import ReportingCurrencySupportService
from .http_errors import value_error_to_http

router = APIRouter(prefix="/reporting-currencies", tags=["Reporting Currency Support"])


@router.get(
    "/support",
    response_model=ReportingCurrencySupportResponse,
    operation_id="get_reporting_currency_support",
    summary="Evaluate reporting-currency support",
    description=(
        "Returns Core's source-owned, portfolio/as-of supportability decision for performance "
        "restatement. Selector presence is reported separately and never implies support. "
        "Authenticated calls are bound to their verified tenant. Trusted internal callers "
        "without an authenticated principal must provide an explicit tenant_id. "
        "UNSUPPORTED means required FX evidence is missing; UNAVAILABLE means the portfolio "
        "source could not be resolved. This contract does not certify downstream lotus-performance "
        "execution or client publication."
    ),
)
async def get_reporting_currency_support(
    request: Request,
    portfolio_id: str = Query(
        ..., min_length=1, description="Portfolio whose source state is evaluated."
    ),
    reporting_currency: str = Query(
        ...,
        min_length=3,
        max_length=3,
        description="Requested three-letter ISO-style reporting currency.",
    ),
    as_of_date: date = Query(
        ...,
        description="Effective date used for portfolio and FX evidence.",
    ),
    tenant_id: str | None = Query(
        None,
        description=(
            "Tenant fence. Required for trusted internal callers without an authenticated "
            "principal; authenticated calls are always bound to their verified tenant."
        ),
    ),
    service: ReportingCurrencySupportService = Depends(get_reporting_currency_support_service),
) -> ReportingCurrencySupportResponse:
    authenticated_tenant_id = getattr(request.state, "enterprise_verified_tenant_id", None)
    normalized_tenant_id = tenant_id.strip() if tenant_id is not None else ""
    if authenticated_tenant_id is not None:
        normalized_authenticated_tenant_id = str(authenticated_tenant_id).strip()
        if not normalized_authenticated_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="authenticated tenant scope is unavailable",
            )
        if normalized_tenant_id and normalized_tenant_id != normalized_authenticated_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="requested tenant does not match authenticated tenant scope",
            )
        normalized_tenant_id = normalized_authenticated_tenant_id
    elif not normalized_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="tenant_id is required when authenticated tenant scope is unavailable",
        )
    try:
        result = await service.evaluate(
            ReportingCurrencySupportQuery(
                portfolio_id=portfolio_id,
                reporting_currency=reporting_currency,
                as_of_date=as_of_date,
                tenant_id=normalized_tenant_id,
            )
        )
    except ValueError as exc:
        raise value_error_to_http(exc, status_code=422) from exc
    return ReportingCurrencySupportResponse(
        contract="ReportingCurrencySupport:v1",
        operation="performance-restatement",
        scope="portfolio-as-of",
        portfolio_id=result.portfolio_id,
        tenant_id=result.tenant_id,
        reporting_currency=result.reporting_currency,
        as_of_date=result.as_of_date,
        status=result.status,
        supported=result.status == "SUPPORTED",
        reason_code=result.reason_code,
        source_currencies=list(result.source_currencies),
        missing_source_currencies=list(result.missing_source_currencies),
        fx_evidence=[
            {
                "source_currency": item.source_currency,
                "rate_date": item.rate_date,
                "rate_available": item.rate_available,
            }
            for item in result.fx_evidence
        ],
        observed_selector_currency=result.observed_selector_currency,
    )
