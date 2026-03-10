from fastapi import APIRouter, Depends, Query
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.lookup_dto import LookupItem, LookupResponse
from ..services.instrument_service import InstrumentService
from ..services.portfolio_service import PortfolioService

router = APIRouter(prefix="/lookups", tags=["Lookup Catalogs"])


async def _fetch_all_instruments(service: InstrumentService, page_limit: int) -> list:
    skip = 0
    collected = []
    while True:
        page = await service.get_instruments(skip=skip, limit=page_limit)
        collected.extend(page.instruments)
        skip += page.limit
        if skip >= page.total:
            break
    return collected


def _filter_limit_sort_items(
    items: list[LookupItem], q: str | None, limit: int
) -> list[LookupItem]:
    if q:
        q_norm = q.strip().upper()
        items = [
            item for item in items if q_norm in item.id.upper() or q_norm in item.label.upper()
        ]
    return sorted(items, key=lambda item: item.id)[:limit]


@router.get(
    "/portfolios",
    response_model=LookupResponse,
    summary="Portfolio Lookup Catalog",
    description=(
        "Returns portfolio selector options for lotus-gateway/UI portfolio selection workflows."
    ),
)
async def get_portfolio_lookups(
    client_id: str | None = Query(
        default=None,
        description="Optional CIF filter for tenant/client scoping.",
        examples=["CIF-100200"],
    ),
    booking_center_code: str | None = Query(
        default=None,
        description="Optional booking-center filter for business-unit specific catalogs.",
        examples=["SGPB"],
    ),
    q: str | None = Query(
        default=None,
        description="Optional case-insensitive search text applied to portfolio ID.",
        examples=["PORT-00"],
    ),
    limit: int = Query(default=500, ge=1, le=1000, examples=[100]),
    db: AsyncSession = Depends(get_async_db_session),
) -> LookupResponse:
    service = PortfolioService(db)
    response = await service.get_portfolios(
        client_id=client_id, booking_center_code=booking_center_code
    )

    items = [
        LookupItem(
            id=portfolio.portfolio_id,
            label=portfolio.portfolio_id,
        )
        for portfolio in response.portfolios
    ]
    return LookupResponse(items=_filter_limit_sort_items(items, q=q, limit=limit))


@router.get(
    "/instruments",
    response_model=LookupResponse,
    summary="Instrument Lookup Catalog",
    description=(
        "Returns instrument selector options for lotus-gateway/UI trade and intake workflows."
    ),
)
async def get_instrument_lookups(
    limit: int = Query(default=200, ge=1, le=1000, examples=[200]),
    product_type: str | None = Query(
        default=None,
        description="Optional product type filter (for example: Equity, Bond).",
        examples=["Equity"],
    ),
    q: str | None = Query(
        default=None,
        description=(
            "Optional case-insensitive search text applied to security ID and instrument name."
        ),
        examples=["AAPL"],
    ),
    db: AsyncSession = Depends(get_async_db_session),
) -> LookupResponse:
    service = InstrumentService(db)
    response = await service.get_instruments(skip=0, limit=limit, product_type=product_type)

    items = [
        LookupItem(
            id=instrument.security_id,
            label=f"{instrument.security_id} | {instrument.name}",
        )
        for instrument in response.instruments
    ]
    return LookupResponse(items=_filter_limit_sort_items(items, q=q, limit=limit))


@router.get(
    "/currencies",
    response_model=LookupResponse,
    summary="Currency Lookup Catalog",
    description=(
        "Returns distinct currency selector options derived from portfolio base currencies "
        "and instrument currencies."
    ),
)
async def get_currency_lookups(
    instrument_page_limit: int = Query(default=500, ge=50, le=1000, examples=[500]),
    source: str = Query(
        default="ALL",
        pattern="^(ALL|PORTFOLIOS|INSTRUMENTS)$",
        description="Currency source scope. Use ALL, PORTFOLIOS, or INSTRUMENTS.",
        examples=["ALL"],
    ),
    q: str | None = Query(
        default=None,
        description="Optional case-insensitive search text applied to currency code.",
        examples=["USD"],
    ),
    limit: int = Query(default=500, ge=1, le=1000, examples=[100]),
    db: AsyncSession = Depends(get_async_db_session),
) -> LookupResponse:
    portfolio_service = PortfolioService(db)
    instrument_service = InstrumentService(db)

    source_scope = source.upper()
    portfolios_response = (
        await portfolio_service.get_portfolios() if source_scope in {"ALL", "PORTFOLIOS"} else None
    )
    instruments = (
        await _fetch_all_instruments(
            service=instrument_service,
            page_limit=instrument_page_limit,
        )
        if source_scope in {"ALL", "INSTRUMENTS"}
        else []
    )

    codes: set[str] = set()
    if portfolios_response:
        codes.update(
            portfolio.base_currency.upper()
            for portfolio in portfolios_response.portfolios
            if portfolio.base_currency
        )
    codes.update({instrument.currency.upper() for instrument in instruments if instrument.currency})

    items = [LookupItem(id=code, label=code) for code in codes]
    return LookupResponse(items=_filter_limit_sort_items(items, q=q, limit=limit))
