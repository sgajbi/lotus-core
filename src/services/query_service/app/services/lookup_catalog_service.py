from ..application.lookup_catalog import (
    CurrencyLookupQuery,
    InstrumentLookupQuery,
    LookupCatalogItem,
    LookupCatalogResult,
    PortfolioLookupQuery,
)
from .instrument_service import InstrumentService
from .portfolio_service import PortfolioService


def _lookup_item_code(item: LookupCatalogItem) -> str:
    return item.id.upper()


def _merge_currency_lookup_items(
    portfolio_items: list[LookupCatalogItem],
    instrument_items: list[LookupCatalogItem],
    *,
    limit: int,
) -> LookupCatalogResult:
    codes = {
        code for item in portfolio_items + instrument_items if (code := _lookup_item_code(item))
    }
    return LookupCatalogResult(
        items=[LookupCatalogItem(id=code, label=code) for code in sorted(codes)[:limit]]
    )


def _lookup_result_from_raw_items(items: list[object]) -> LookupCatalogResult:
    return LookupCatalogResult(items=[LookupCatalogItem.from_raw(item) for item in items])


class LookupCatalogService:
    def __init__(
        self,
        *,
        portfolio_service: PortfolioService,
        instrument_service: InstrumentService,
    ):
        self._portfolio_service = portfolio_service
        self._instrument_service = instrument_service

    async def search_portfolio_lookup_items(
        self,
        query: PortfolioLookupQuery,
    ) -> LookupCatalogResult:
        return _lookup_result_from_raw_items(
            await self._portfolio_service.search_portfolio_lookup_items(
                client_id=query.client_id,
                booking_center_code=query.booking_center_code,
                q=query.q,
                limit=query.limit,
            )
        )

    async def search_instrument_lookup_items(
        self,
        query: InstrumentLookupQuery,
    ) -> LookupCatalogResult:
        return _lookup_result_from_raw_items(
            await self._instrument_service.search_instrument_lookup_items(
                product_type=query.product_type,
                q=query.q,
                limit=query.limit,
            )
        )

    async def list_currency_lookup_items(
        self,
        query: CurrencyLookupQuery,
    ) -> LookupCatalogResult:
        source_scope = query.source.upper()
        portfolio_items = (
            _lookup_result_from_raw_items(
                await self._portfolio_service.list_currency_lookup_items(
                    q=query.q, limit=query.limit
                )
            ).items
            if source_scope in {"ALL", "PORTFOLIOS"}
            else []
        )
        instrument_items = (
            _lookup_result_from_raw_items(
                await self._instrument_service.list_currency_lookup_items(
                    q=query.q, limit=query.limit
                )
            ).items
            if source_scope in {"ALL", "INSTRUMENTS"}
            else []
        )

        return _merge_currency_lookup_items(
            portfolio_items,
            instrument_items,
            limit=query.limit,
        )
