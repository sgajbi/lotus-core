"""Tests for correction-safe bulk market-price authority resolution."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import MarketPriceSourceFactRecord
from portfolio_common.domain.valuation import (
    MissingMarketPriceSourceFactError,
    OverlappingMarketPriceSourceFactError,
    ValuationAuthorityScope,
)
from sqlalchemy.dialects import postgresql

from src.services.calculators.position_valuation_calculator.app.infrastructure import (
    MARKET_PRICE_AUTHORITY_QUERY_CHUNK_SIZE,
    MAX_MARKET_PRICE_AUTHORITY_REQUESTS,
    SqlAlchemyMarketPriceSourceFactResolver,
)
from src.services.calculators.position_valuation_calculator.app.ports import (
    MarketPriceAuthorityRequest,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


def _record(**overrides: object) -> MarketPriceSourceFactRecord:
    values: dict[str, object] = {
        "tenant_id": "LOTUS_PB_SG",
        "legal_book_id": "SG_PRIVATE_BANK_BOOK",
        "security_id": "BOND_US_CORP_2031",
        "price_date": date(2026, 7, 22),
        "price": Decimal("99.25"),
        "currency": "USD",
        "quote_basis": "PERCENT_OF_PRINCIPAL_CLEAN",
        "fact_status": "ACTIVE",
        "fact_version": 2,
        "source_system": "approved_market_data",
        "source_record_id": "PRICE-001",
        "source_revision": "revision-2",
        "source_content_hash": "a" * 64,
        "observed_at": datetime(2026, 7, 23, 4, 30, tzinfo=UTC),
    }
    values.update(overrides)
    return MarketPriceSourceFactRecord(**values)


def _request(**scope_overrides: str) -> MarketPriceAuthorityRequest:
    scope = {
        "tenant_id": "LOTUS_PB_SG",
        "legal_book_id": "SG_PRIVATE_BANK_BOOK",
        "security_id": "BOND_US_CORP_2031",
    }
    scope.update(scope_overrides)
    return MarketPriceAuthorityRequest(
        scope=ValuationAuthorityScope(**scope),
        price_date=date(2026, 7, 22),
    )


def _session_returning(*records: MarketPriceSourceFactRecord) -> AsyncMock:
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(all=lambda: list(records))
    return session


async def test_resolve_many_ranks_stable_sources_before_current_scope_in_one_query() -> None:
    request = _request()
    session = _session_returning(_record())
    resolver = SqlAlchemyMarketPriceSourceFactResolver(session)

    resolved = await resolver.resolve_many([request, request])

    assert list(resolved) == [request.key]
    assert resolved[request.key].price == Decimal("99.25")
    assert resolved[request.key].fact_version == 2
    assert resolved[request.key].source_record_key == ("approved_market_data", "PRICE-001")
    session.scalars.assert_awaited_once()

    statement = session.scalars.await_args.args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "candidate_market_price_sources" in compiled
    assert "SELECT DISTINCT" in compiled
    assert "row_number() OVER" in compiled
    assert (
        "PARTITION BY market_price_source_facts.source_system, "
        "market_price_source_facts.source_record_id" in compiled
    )
    assert "market_price_source_facts.fact_version DESC" in compiled
    assert "source_rank" in compiled


async def test_resolve_many_returns_multiple_exact_authorities_without_n_plus_one() -> None:
    first = _request()
    second = _request(security_id="BOND_US_CORP_2032")
    session = _session_returning(
        _record(),
        _record(
            security_id="BOND_US_CORP_2032",
            source_record_id="PRICE-002",
            price=Decimal("101.75"),
        ),
    )

    resolved = await SqlAlchemyMarketPriceSourceFactResolver(session).resolve_many([first, second])

    assert resolved[first.key].price == Decimal("99.25")
    assert resolved[second.key].price == Decimal("101.75")
    session.scalars.assert_awaited_once()


async def test_resolve_many_fails_closed_when_latest_source_moved_away() -> None:
    request = _request()
    resolver = SqlAlchemyMarketPriceSourceFactResolver(_session_returning())

    with pytest.raises(MissingMarketPriceSourceFactError, match="exact tenant"):
        await resolver.resolve_many([request])


async def test_resolve_many_fails_closed_for_competing_current_sources() -> None:
    request = _request()
    resolver = SqlAlchemyMarketPriceSourceFactResolver(
        _session_returning(
            _record(),
            _record(
                source_system="second_approved_market_data",
                source_record_id="PRICE-991",
            ),
        )
    )

    with pytest.raises(OverlappingMarketPriceSourceFactError, match="overlapping active"):
        await resolver.resolve_many([request])


async def test_resolve_many_empty_batch_avoids_database_access() -> None:
    session = _session_returning()

    assert await SqlAlchemyMarketPriceSourceFactResolver(session).resolve_many([]) == {}
    session.scalars.assert_not_awaited()


@pytest.mark.parametrize(
    ("request_count", "expected_queries"),
    [
        (MARKET_PRICE_AUTHORITY_QUERY_CHUNK_SIZE, 1),
        (MARKET_PRICE_AUTHORITY_QUERY_CHUNK_SIZE + 1, 2),
        (
            MAX_MARKET_PRICE_AUTHORITY_REQUESTS,
            MAX_MARKET_PRICE_AUTHORITY_REQUESTS // MARKET_PRICE_AUTHORITY_QUERY_CHUNK_SIZE,
        ),
    ],
)
async def test_resolve_many_chunks_bounded_request_batches(
    request_count: int,
    expected_queries: int,
) -> None:
    requests = [
        _request(security_id=f"BOND-BOUNDARY-{index:03d}") for index in range(request_count)
    ]
    session = _session_returning()

    with pytest.raises(MissingMarketPriceSourceFactError):
        await SqlAlchemyMarketPriceSourceFactResolver(session).resolve_many(requests)

    assert session.scalars.await_count == expected_queries


async def test_resolve_many_merges_chunk_results_after_one_global_deduplication() -> None:
    request_count = MARKET_PRICE_AUTHORITY_QUERY_CHUNK_SIZE + 1
    requests = [_request(security_id=f"BOND-MERGED-{index:03d}") for index in range(request_count)]
    records = [
        _record(
            security_id=request.scope.security_id,
            source_record_id=f"PRICE-MERGED-{index:03d}",
        )
        for index, request in enumerate(requests)
    ]
    session = AsyncMock()
    session.scalars.side_effect = [
        SimpleNamespace(all=lambda: records[:MARKET_PRICE_AUTHORITY_QUERY_CHUNK_SIZE]),
        SimpleNamespace(all=lambda: records[MARKET_PRICE_AUTHORITY_QUERY_CHUNK_SIZE:]),
    ]

    resolved = await SqlAlchemyMarketPriceSourceFactResolver(session).resolve_many(
        [*requests, requests[0]]
    )

    assert list(resolved) == [request.key for request in requests]
    assert resolved[requests[0].key].source_record_key == (
        "approved_market_data",
        "PRICE-MERGED-000",
    )
    assert resolved[requests[-1].key].source_record_key == (
        "approved_market_data",
        f"PRICE-MERGED-{request_count - 1:03d}",
    )
    assert session.scalars.await_count == 2


async def test_resolve_many_rejects_request_batch_above_ceiling_before_query() -> None:
    requests = [
        _request(security_id=f"BOND-OVERFLOW-{index:03d}")
        for index in range(MAX_MARKET_PRICE_AUTHORITY_REQUESTS + 1)
    ]
    session = _session_returning()

    with pytest.raises(ValueError, match="request batch exceeds 500"):
        await SqlAlchemyMarketPriceSourceFactResolver(session).resolve_many(requests)

    session.scalars.assert_not_awaited()


async def test_market_price_authority_request_rejects_invalid_scope_and_date() -> None:
    with pytest.raises(TypeError, match="scope must be"):
        MarketPriceAuthorityRequest(  # type: ignore[arg-type]
            scope={"tenant_id": "LOTUS_PB_SG"},
            price_date=date(2026, 7, 22),
        )
    with pytest.raises(TypeError, match="price_date must be an exact date"):
        MarketPriceAuthorityRequest(  # type: ignore[arg-type]
            scope=ValuationAuthorityScope(
                "LOTUS_PB_SG",
                "SG_PRIVATE_BANK_BOOK",
                "BOND_US_CORP_2031",
            ),
            price_date=datetime(2026, 7, 22, tzinfo=UTC),
        )
