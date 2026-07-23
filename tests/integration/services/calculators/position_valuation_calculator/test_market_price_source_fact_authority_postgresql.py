"""PostgreSQL proof for correction-safe market-price write/read authority."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Instrument,
    MarketPriceSourceFactRecord,
)
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    MarketPriceSourceFactStatus,
    MissingMarketPriceSourceFactError,
    OverlappingMarketPriceSourceFactError,
    ValuationAuthorityScope,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.calculators.position_valuation_calculator.app.infrastructure import (
    SqlAlchemyMarketPriceSourceFactResolver,
)
from src.services.calculators.position_valuation_calculator.app.ports import (
    MarketPriceAuthorityRequest,
)
from src.services.ingestion_service.app.services.market_price_source_fact_writer import (
    MarketPriceSourceFactWriter,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

PRICE_DATE = date(2026, 7, 22)
OLD_SECURITY_ID = "AUTH-MOVE-OLD"
NEW_SECURITY_ID = "AUTH-MOVE-NEW"


def _fact(
    *,
    source_record_id: str = "PRICE-MOVE-001",
    fact_version: int,
    security_id: str,
    status: MarketPriceSourceFactStatus,
) -> MarketPriceSourceFact:
    return MarketPriceSourceFact(
        scope=ValuationAuthorityScope(
            tenant_id="TENANT-AUTH",
            legal_book_id="BOOK-AUTH",
            security_id=security_id,
        ),
        price_date=PRICE_DATE,
        price=Decimal("99.25"),
        currency="USD",
        quote_basis=MarketPriceQuoteBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        source_reference=FinancialSourceReference(
            source_system="approved-market-data",
            source_record_id=source_record_id,
            source_revision=f"revision-{fact_version}",
            source_content_hash=f"{fact_version:064x}",
            observed_at=datetime(2026, 7, 22, fact_version, tzinfo=UTC),
        ),
        fact_status=status,
        fact_version=fact_version,
    )


def _request(security_id: str) -> MarketPriceAuthorityRequest:
    return MarketPriceAuthorityRequest(
        scope=ValuationAuthorityScope(
            tenant_id="TENANT-AUTH",
            legal_book_id="BOOK-AUTH",
            security_id=security_id,
        ),
        price_date=PRICE_DATE,
    )


async def _seed_instruments(session: AsyncSession) -> None:
    session.add_all(
        [
            Instrument(
                security_id=security_id,
                name=f"Authority proof {security_id}",
                isin=isin,
                currency="USD",
                product_type="BOND",
                asset_class="FIXED_INCOME",
            )
            for security_id, isin in [
                (OLD_SECURITY_ID, "XS451AUTH0001"),
                (NEW_SECURITY_ID, "XS451AUTH0002"),
            ]
        ]
    )
    await session.commit()


async def _assert_missing(
    resolver: SqlAlchemyMarketPriceSourceFactResolver,
    security_id: str,
) -> None:
    with pytest.raises(MissingMarketPriceSourceFactError):
        await resolver.resolve_many([_request(security_id)])


async def test_moved_active_suspended_and_retired_corrections_fence_old_authority(
    clean_db: None,
    async_db_session: AsyncSession,
) -> None:
    await _seed_instruments(async_db_session)
    writer = MarketPriceSourceFactWriter(async_db_session)
    resolver = SqlAlchemyMarketPriceSourceFactResolver(async_db_session)

    first = _fact(
        fact_version=1,
        security_id=OLD_SECURITY_ID,
        status=MarketPriceSourceFactStatus.ACTIVE,
    )
    await writer.append_many([first])
    await async_db_session.commit()
    assert (await resolver.resolve_many([_request(OLD_SECURITY_ID)]))[
        _request(OLD_SECURITY_ID).key
    ] == first

    moved_active = _fact(
        fact_version=2,
        security_id=NEW_SECURITY_ID,
        status=MarketPriceSourceFactStatus.ACTIVE,
    )
    changes = await writer.append_many([moved_active])
    await async_db_session.commit()
    assert changes[0].affected_authorities == {
        _request(OLD_SECURITY_ID).key,
        _request(NEW_SECURITY_ID).key,
    }
    await _assert_missing(resolver, OLD_SECURITY_ID)
    assert (await resolver.resolve_many([_request(NEW_SECURITY_ID)]))[
        _request(NEW_SECURITY_ID).key
    ] == moved_active

    moved_suspended = _fact(
        fact_version=3,
        security_id=OLD_SECURITY_ID,
        status=MarketPriceSourceFactStatus.SUSPENDED,
    )
    await writer.append_many([moved_suspended])
    await async_db_session.commit()
    await _assert_missing(resolver, OLD_SECURITY_ID)
    await _assert_missing(resolver, NEW_SECURITY_ID)

    restored = _fact(
        fact_version=4,
        security_id=NEW_SECURITY_ID,
        status=MarketPriceSourceFactStatus.ACTIVE,
    )
    moved_retired = _fact(
        fact_version=5,
        security_id=OLD_SECURITY_ID,
        status=MarketPriceSourceFactStatus.RETIRED,
    )
    await writer.append_many([restored])
    await writer.append_many([moved_retired])
    await async_db_session.commit()
    await _assert_missing(resolver, OLD_SECURITY_ID)
    await _assert_missing(resolver, NEW_SECURITY_ID)

    assert (await async_db_session.scalar(select(func.count(MarketPriceSourceFactRecord.id)))) == 5


async def test_concurrent_competing_sources_serialize_to_one_active_authority(
    clean_db: None,
    async_db_session: AsyncSession,
) -> None:
    await _seed_instruments(async_db_session)
    sessions = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def _append(source_record_id: str) -> None:
        async with sessions() as session:
            try:
                await MarketPriceSourceFactWriter(session).append_many(
                    [
                        _fact(
                            source_record_id=source_record_id,
                            fact_version=1,
                            security_id=OLD_SECURITY_ID,
                            status=MarketPriceSourceFactStatus.ACTIVE,
                        )
                    ]
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    results = await asyncio.wait_for(
        asyncio.gather(
            _append("PRICE-CONCURRENT-A"),
            _append("PRICE-CONCURRENT-B"),
            return_exceptions=True,
        ),
        timeout=10,
    )

    assert sum(result is None for result in results) == 1
    failures = [result for result in results if result is not None]
    assert len(failures) == 1
    assert isinstance(failures[0], OverlappingMarketPriceSourceFactError)
    assert (await async_db_session.scalar(select(func.count(MarketPriceSourceFactRecord.id)))) == 1

    await async_db_session.execute(delete(MarketPriceSourceFactRecord))
    await async_db_session.commit()


async def test_concurrent_move_and_new_claim_preserve_one_new_authority(
    clean_db: None,
    async_db_session: AsyncSession,
) -> None:
    await _seed_instruments(async_db_session)
    initial = _fact(
        fact_version=1,
        security_id=OLD_SECURITY_ID,
        status=MarketPriceSourceFactStatus.ACTIVE,
    )
    await MarketPriceSourceFactWriter(async_db_session).append_many([initial])
    await async_db_session.commit()
    sessions = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    moved = _fact(
        fact_version=2,
        security_id=NEW_SECURITY_ID,
        status=MarketPriceSourceFactStatus.ACTIVE,
    )
    competing = _fact(
        source_record_id="PRICE-MOVE-COMPETING",
        fact_version=1,
        security_id=NEW_SECURITY_ID,
        status=MarketPriceSourceFactStatus.ACTIVE,
    )

    async def _append(fact: MarketPriceSourceFact) -> None:
        async with sessions() as session:
            try:
                await MarketPriceSourceFactWriter(session).append_many([fact])
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    results = await asyncio.wait_for(
        asyncio.gather(
            _append(moved),
            _append(competing),
            return_exceptions=True,
        ),
        timeout=10,
    )

    assert sum(result is None for result in results) == 1
    failures = [result for result in results if result is not None]
    assert len(failures) == 1
    assert isinstance(failures[0], OverlappingMarketPriceSourceFactError)

    resolver = SqlAlchemyMarketPriceSourceFactResolver(async_db_session)
    new_authority = (await resolver.resolve_many([_request(NEW_SECURITY_ID)]))[
        _request(NEW_SECURITY_ID).key
    ]
    if new_authority.source_record_key == moved.source_record_key:
        assert new_authority == moved
        await _assert_missing(resolver, OLD_SECURITY_ID)
    else:
        assert new_authority == competing
        assert (await resolver.resolve_many([_request(OLD_SECURITY_ID)]))[
            _request(OLD_SECURITY_ID).key
        ] == initial

    assert (await async_db_session.scalar(select(func.count(MarketPriceSourceFactRecord.id)))) == 2
