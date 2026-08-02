"""Supportability API for effective-dated fixed-income book cost."""

from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status

from ..dependencies import get_fixed_income_book_cost_service
from ..dtos.fixed_income_book_cost_dto import FixedIncomeBookCostAsOfResponse
from ..services.fixed_income_book_cost_service import FixedIncomeBookCostService
from .http_errors import lookup_error_to_http

router = APIRouter(prefix="/portfolios", tags=["Fixed-Income Book Cost"])


@router.get(
    "/{portfolio_id}/positions/{security_id}/lots/{lot_id}/book-cost",
    response_model=FixedIncomeBookCostAsOfResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "No profile is effective for the exact source-lot scope and date.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": (
                            "fixed-income book-cost profile not found for exact "
                            "tenant/legal-book/portfolio/security/lot scope and as-of date"
                        )
                    }
                }
            },
        }
    },
    summary="Get fixed-income lot book cost as of a date",
    description=(
        "Returns the latest persisted amortized-cost profile effective for one exact tenant, "
        "legal book, portfolio, security and source lot. The response identifies the recognized "
        "book cost at completed schedule boundaries, the next recognition date, immutable source "
        "references, profile hashes and input/calculation/output lineage. PARKED profiles return "
        "their explicit eligibility reason and no calculated amount. This is book-cost "
        "supportability evidence, not a market valuation, tax basis, dirty price or inferred "
        "principal calculation."
    ),
)
async def get_fixed_income_book_cost_as_of(
    portfolio_id: str = Path(
        ...,
        min_length=1,
        description="Portfolio identifier within the governed legal book.",
        examples=["PORTFOLIO_001"],
    ),
    security_id: str = Path(
        ...,
        min_length=1,
        description="Security identifier held by the source lot.",
        examples=["BOND_001"],
    ),
    lot_id: str = Path(
        ...,
        min_length=1,
        description="Source-owned position lot identifier.",
        examples=["LOT_001"],
    ),
    tenant_id: str = Query(
        ...,
        min_length=1,
        description="Tenant identifier required for exact-scope isolation.",
        examples=["TENANT_SG"],
    ),
    legal_book_id: str = Query(
        ...,
        min_length=1,
        description="Legal-book identifier required for exact-scope isolation.",
        examples=["BOOK_SG_PB"],
    ),
    as_of_date: date = Query(
        ...,
        description="Governed business date for effective profile and period recognition.",
        examples=["2026-12-31"],
    ),
    x_tenant_id: str = Header(
        ...,
        min_length=1,
        description="Authenticated tenant scope; must match the requested tenant.",
        examples=["TENANT_SG"],
    ),
    service: FixedIncomeBookCostService = Depends(get_fixed_income_book_cost_service),
) -> FixedIncomeBookCostAsOfResponse:
    normalized_tenant_id = tenant_id.strip()
    normalized_authenticated_tenant_id = x_tenant_id.strip()
    if not normalized_tenant_id or not normalized_authenticated_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="tenant identifiers must not be blank",
        )
    if normalized_tenant_id != normalized_authenticated_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requested tenant does not match authenticated tenant scope",
        )
    try:
        response = await service.get_as_of(
            tenant_id=normalized_tenant_id,
            legal_book_id=legal_book_id,
            portfolio_id=portfolio_id,
            security_id=security_id,
            lot_id=lot_id,
            as_of_date=as_of_date,
        )
        if not isinstance(response, FixedIncomeBookCostAsOfResponse):
            raise TypeError("book-cost service returned an unsupported response type")
        return response
    except LookupError as exc:
        raise lookup_error_to_http(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
