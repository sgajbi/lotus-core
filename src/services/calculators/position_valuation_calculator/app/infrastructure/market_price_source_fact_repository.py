"""SQLAlchemy adapter for correction-safe market-price authority resolution."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from portfolio_common.database_models import MarketPriceSourceFactRecord
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    MarketPriceSourceFactStatus,
    ValuationAuthorityScope,
    resolve_market_price_source_fact,
)
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..ports import (
    MarketPriceAuthorityKey,
    MarketPriceAuthorityRequest,
)

MAX_MARKET_PRICE_AUTHORITY_REQUESTS = 500
MARKET_PRICE_AUTHORITY_QUERY_CHUNK_SIZE = 100
_Value = TypeVar("_Value")


class SqlAlchemyMarketPriceSourceFactResolver:
    """Resolve a batch after ranking stable source identities before current scope."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve_many(
        self,
        requests: Sequence[MarketPriceAuthorityRequest],
    ) -> dict[MarketPriceAuthorityKey, MarketPriceSourceFact]:
        """Return one authoritative fact per deduplicated exact request in one query."""

        if len(requests) > MAX_MARKET_PRICE_AUTHORITY_REQUESTS:
            raise ValueError(
                "market-price authority request batch exceeds "
                f"{MAX_MARKET_PRICE_AUTHORITY_REQUESTS}"
            )
        request_by_key = {request.key: request for request in requests}
        if not request_by_key:
            return {}

        record = MarketPriceSourceFactRecord
        rows: list[MarketPriceSourceFactRecord] = []
        for requested_keys in _chunks(
            list(request_by_key),
            MARKET_PRICE_AUTHORITY_QUERY_CHUNK_SIZE,
        ):
            candidate_sources = (
                select(record.source_system, record.source_record_id)
                .where(
                    tuple_(
                        record.tenant_id,
                        record.legal_book_id,
                        record.security_id,
                        record.price_date,
                    ).in_(requested_keys)
                )
                .distinct()
                .cte("candidate_market_price_sources")
            )
            source_rank = (
                func.row_number()
                .over(
                    partition_by=(record.source_system, record.source_record_id),
                    order_by=record.fact_version.desc(),
                )
                .label("source_rank")
            )
            ranked_source_versions = (
                select(record, source_rank)
                .join(
                    candidate_sources,
                    and_(
                        record.source_system == candidate_sources.c.source_system,
                        record.source_record_id == candidate_sources.c.source_record_id,
                    ),
                )
                .subquery()
            )
            latest_record = aliased(record, ranked_source_versions)
            statement = select(latest_record).where(
                ranked_source_versions.c.source_rank == 1,
                tuple_(
                    latest_record.tenant_id,
                    latest_record.legal_book_id,
                    latest_record.security_id,
                    latest_record.price_date,
                ).in_(requested_keys),
            )
            rows.extend((await self._db.scalars(statement)).all())

        facts_by_key: dict[MarketPriceAuthorityKey, list[MarketPriceSourceFact]] = {}
        for row in rows:
            fact = _fact_from_record(row)
            facts_by_key.setdefault((*fact.scope.key, fact.price_date), []).append(fact)

        resolved: dict[MarketPriceAuthorityKey, MarketPriceSourceFact] = {}
        for key, request in request_by_key.items():
            resolved[key] = resolve_market_price_source_fact(
                facts_by_key.get(key, []),
                tenant_id=request.scope.tenant_id,
                legal_book_id=request.scope.legal_book_id,
                security_id=request.scope.security_id,
                price_date=request.price_date,
            )
        return resolved


def _chunks(values: list[_Value], size: int) -> list[list[_Value]]:
    return [values[offset : offset + size] for offset in range(0, len(values), size)]


def _fact_from_record(record: MarketPriceSourceFactRecord) -> MarketPriceSourceFact:
    return MarketPriceSourceFact(
        scope=ValuationAuthorityScope(
            tenant_id=record.tenant_id,
            legal_book_id=record.legal_book_id,
            security_id=record.security_id,
        ),
        price_date=record.price_date,
        price=record.price,
        currency=record.currency,
        quote_basis=MarketPriceQuoteBasis(record.quote_basis),
        source_reference=FinancialSourceReference(
            source_system=record.source_system,
            source_record_id=record.source_record_id,
            source_revision=record.source_revision,
            source_content_hash=record.source_content_hash,
            observed_at=record.observed_at,
        ),
        fact_status=MarketPriceSourceFactStatus(record.fact_status),
        fact_version=record.fact_version,
    )
