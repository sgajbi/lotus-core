from fastapi import APIRouter, Depends, Query
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.lookup_dto import LookupItem, LookupResponse
from ..services.instrument_service import InstrumentService
from ..services.portfolio_service import PortfolioService

router = APIRouter(prefix="/lookups", tags=["Lookup Catalogs"])


def _lookup_item_code(item: LookupItem | dict) -> str:
    if isinstance(item, dict):
        return str(item.get("id", "")).upper()
    return item.id.upper()


def _merge_currency_lookup_items(
    portfolio_items: list[LookupItem | dict],
    instrument_items: list[LookupItem | dict],
    *,
    limit: int,
) -> list[LookupItem]:
    codes = {
        code for item in portfolio_items + instrument_items if (code := _lookup_item_code(item))
    }
    return [LookupItem(id=code, label=code) for code in sorted(codes)[:limit]]


@router.get(
    "/portfolios",
    response_model=LookupResponse,
    summary="Get portfolio selector catalog",
    description=(
        "Returns portfolio selector options for lotus-gateway and UI portfolio selection "
        "workflows. Use this route for thin selector catalogs only; do not use it as a substitute "
        "for canonical portfolio detail or broader portfolio-state reads."
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
    limit: int = Query(
        default=500,
        ge=1,
        le=1000,
        description="Maximum number of lookup items to return after filtering and sorting.",
        examples=[100],
    ),
    db: AsyncSession = Depends(get_async_db_session),
) -> LookupResponse:
    service = PortfolioService(db)
    items = await service.search_portfolio_lookup_items(
        client_id=client_id,
        booking_center_code=booking_center_code,
        q=q,
        limit=limit,
    )
    return LookupResponse(items=items)


@router.get(
    "/instruments",
    response_model=LookupResponse,
    summary="Get instrument selector catalog",
    description=(
        "Returns instrument selector options for lotus-gateway and UI trade/intake workflows. Use "
        "this route for thin selector catalogs only; do not use it as a substitute for canonical "
        "instrument reference reads or enrichment output."
    ),
)
async def get_instrument_lookups(
    limit: int = Query(
        default=200,
        ge=1,
        le=1000,
        description="Maximum number of instrument lookup items to return.",
        examples=[200],
    ),
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
    items = await service.search_instrument_lookup_items(
        product_type=product_type,
        q=q,
        limit=limit,
    )
    return LookupResponse(items=items)


@router.get(
    "/currencies",
    response_model=LookupResponse,
    summary="Get currency selector catalog",
    description=(
        "Returns distinct currency selector options derived from portfolio base currencies "
        "and instrument currencies. Use this route for selector population only; do not use it as "
        "a substitute for FX-rate history or broader market-data contracts."
    ),
)
async def get_currency_lookups(
    instrument_page_limit: int = Query(
        default=500,
        ge=50,
        le=1000,
        deprecated=True,
        description=(
            "Deprecated compatibility parameter. Currency lookups now use bounded selector queries "
            "instead of instrument catalog scans."
        ),
        examples=[500],
    ),
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
    limit: int = Query(
        default=500,
        ge=1,
        le=1000,
        description="Maximum number of currency lookup items to return after filtering.",
        examples=[100],
    ),
    db: AsyncSession = Depends(get_async_db_session),
) -> LookupResponse:
    portfolio_service = PortfolioService(db)
    instrument_service = InstrumentService(db)
    _ = instrument_page_limit

    source_scope = source.upper()
    portfolio_items = (
        await portfolio_service.list_currency_lookup_items(q=q, limit=limit)
        if source_scope in {"ALL", "PORTFOLIOS"}
        else []
    )
    instrument_items = (
        await instrument_service.list_currency_lookup_items(q=q, limit=limit)
        if source_scope in {"ALL", "INSTRUMENTS"}
        else []
    )

    return LookupResponse(
        items=_merge_currency_lookup_items(
            portfolio_items,
            instrument_items,
            limit=limit,
        )
    )
