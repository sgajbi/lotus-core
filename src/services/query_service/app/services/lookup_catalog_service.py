from ..dtos.lookup_dto import LookupItem
from .instrument_service import InstrumentService
from .portfolio_service import PortfolioService


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
        *,
        client_id: str | None = None,
        booking_center_code: str | None = None,
        q: str | None = None,
        limit: int,
    ) -> list[LookupItem]:
        return await self._portfolio_service.search_portfolio_lookup_items(
            client_id=client_id,
            booking_center_code=booking_center_code,
            q=q,
            limit=limit,
        )

    async def search_instrument_lookup_items(
        self,
        *,
        product_type: str | None = None,
        q: str | None = None,
        limit: int,
    ) -> list[LookupItem]:
        return await self._instrument_service.search_instrument_lookup_items(
            product_type=product_type,
            q=q,
            limit=limit,
        )

    async def list_currency_lookup_items(
        self,
        *,
        source: str,
        q: str | None = None,
        limit: int,
    ) -> list[LookupItem]:
        source_scope = source.upper()
        portfolio_items = (
            await self._portfolio_service.list_currency_lookup_items(q=q, limit=limit)
            if source_scope in {"ALL", "PORTFOLIOS"}
            else []
        )
        instrument_items = (
            await self._instrument_service.list_currency_lookup_items(q=q, limit=limit)
            if source_scope in {"ALL", "INSTRUMENTS"}
            else []
        )

        return _merge_currency_lookup_items(
            portfolio_items,
            instrument_items,
            limit=limit,
        )
