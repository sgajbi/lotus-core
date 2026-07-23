"""Tests for correction-safe append-only market-price authority writes."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    MarketPriceSourceFactError,
    MarketPriceSourceFactStatus,
    OverlappingMarketPriceSourceFactError,
    ValuationAuthorityScope,
)

from src.services.ingestion_service.app.services.market_price_source_fact_writer import (
    MAX_MARKET_PRICE_SOURCE_FACT_WRITE_BATCH,
    MarketPriceSourceFactWriter,
)

pytestmark = pytest.mark.asyncio


def _fact(
    *,
    source_record_id: str = "PRICE-001",
    fact_version: int = 1,
    security_id: str = "BOND-OLD",
    status: MarketPriceSourceFactStatus = MarketPriceSourceFactStatus.ACTIVE,
    price: str = "99.25",
) -> MarketPriceSourceFact:
    return MarketPriceSourceFact(
        scope=ValuationAuthorityScope(
            tenant_id="TENANT-SG",
            legal_book_id="PB-SG-01",
            security_id=security_id,
        ),
        price_date=date(2026, 7, 22),
        price=Decimal(price),
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


def _record(fact: MarketPriceSourceFact) -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=fact.scope.tenant_id,
        legal_book_id=fact.scope.legal_book_id,
        security_id=fact.scope.security_id,
        price_date=fact.price_date,
        price=fact.price,
        currency=fact.currency,
        quote_basis=fact.quote_basis.value,
        fact_status=fact.fact_status.value,
        fact_version=fact.fact_version,
        source_system=fact.source_reference.source_system,
        source_record_id=fact.source_reference.source_record_id,
        source_revision=fact.source_reference.source_revision,
        source_content_hash=fact.source_reference.source_content_hash,
        observed_at=fact.source_reference.observed_at,
    )


def _result(rows: list[Any]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def _db(
    *,
    incoming_history: list[MarketPriceSourceFact],
    candidate_sources: list[tuple[str, str]],
    candidate_history: list[MarketPriceSourceFact],
) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.scalars = AsyncMock(
        side_effect=[
            _result([_record(fact) for fact in incoming_history]),
            _result([_record(fact) for fact in candidate_history]),
        ]
    )
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    db.execute.return_value = _result(candidate_sources)
    return db


async def test_append_returns_old_and_new_authorities_for_moved_correction() -> None:
    previous = _fact()
    corrected = _fact(fact_version=2, security_id="BOND-NEW")
    db = _db(
        incoming_history=[previous],
        candidate_sources=[previous.source_record_key],
        candidate_history=[previous],
    )

    changes = await MarketPriceSourceFactWriter(db).append_many([corrected])

    assert len(changes) == 1
    assert changes[0].previous == previous
    assert changes[0].accepted == corrected
    assert changes[0].affected_authorities == {
        (*previous.scope.key, previous.price_date),
        (*corrected.scope.key, corrected.price_date),
    }
    assert db.execute.await_count == 4
    db.add_all.assert_called_once()
    db.flush.assert_awaited_once()


async def test_exact_durable_replay_is_an_insert_free_noop() -> None:
    fact = _fact()
    db = _db(
        incoming_history=[fact],
        candidate_sources=[],
        candidate_history=[],
    )

    assert await MarketPriceSourceFactWriter(db).append_many([fact]) == ()

    assert db.execute.await_count == 1
    assert db.scalars.await_count == 1
    db.add_all.assert_not_called()
    db.flush.assert_not_awaited()


async def test_divergent_durable_replay_fails_closed() -> None:
    durable = _fact()
    divergent = _fact(price="100.00")
    db = _db(
        incoming_history=[durable],
        candidate_sources=[],
        candidate_history=[],
    )

    with pytest.raises(
        MarketPriceSourceFactError,
        match="conflicting payloads share one source record and fact_version",
    ):
        await MarketPriceSourceFactWriter(db).append_many([divergent])

    db.add_all.assert_not_called()


async def test_stale_unseen_version_fails_closed() -> None:
    durable = _fact(fact_version=3)
    stale = _fact(fact_version=2)
    db = _db(
        incoming_history=[durable],
        candidate_sources=[],
        candidate_history=[],
    )

    with pytest.raises(
        MarketPriceSourceFactError,
        match="correction version must be newer",
    ):
        await MarketPriceSourceFactWriter(db).append_many([stale])

    db.add_all.assert_not_called()


async def test_out_of_order_new_history_is_appended_and_reported_in_version_order() -> None:
    second = _fact(
        fact_version=2,
        status=MarketPriceSourceFactStatus.RETIRED,
    )
    third = _fact(
        fact_version=3,
        security_id="BOND-NEW",
        status=MarketPriceSourceFactStatus.RETIRED,
    )
    db = _db(
        incoming_history=[],
        candidate_sources=[],
        candidate_history=[],
    )

    changes = await MarketPriceSourceFactWriter(db).append_many([third, second])

    assert [(change.previous, change.accepted) for change in changes] == [
        (None, second),
        (second, third),
    ]
    inserted = db.add_all.call_args.args[0]
    assert [record.fact_version for record in inserted] == [2, 3]


async def test_competing_active_source_fails_before_insert() -> None:
    competing = _fact(source_record_id="PRICE-COMPETING")
    incoming = _fact()
    db = _db(
        incoming_history=[],
        candidate_sources=[competing.source_record_key],
        candidate_history=[competing],
    )

    with pytest.raises(
        OverlappingMarketPriceSourceFactError,
        match="multiple active market-price source records",
    ):
        await MarketPriceSourceFactWriter(db).append_many([incoming])

    db.add_all.assert_not_called()
    db.flush.assert_not_awaited()


async def test_historical_competing_claim_does_not_revive_after_source_moves() -> None:
    competing_old = _fact(source_record_id="PRICE-COMPETING")
    competing_moved = _fact(
        source_record_id="PRICE-COMPETING",
        fact_version=2,
        security_id="BOND-OTHER",
    )
    incoming = _fact()
    db = _db(
        incoming_history=[],
        candidate_sources=[competing_old.source_record_key],
        candidate_history=[competing_old, competing_moved],
    )

    changes = await MarketPriceSourceFactWriter(db).append_many([incoming])

    assert changes[0].accepted == incoming
    db.add_all.assert_called_once()
    db.flush.assert_awaited_once()


async def test_duplicate_source_version_in_one_batch_fails_before_locking() -> None:
    fact = _fact()
    db = _db(
        incoming_history=[],
        candidate_sources=[],
        candidate_history=[],
    )

    with pytest.raises(
        MarketPriceSourceFactError,
        match="batch contains duplicate source versions",
    ):
        await MarketPriceSourceFactWriter(db).append_many([fact, fact])

    db.execute.assert_not_awaited()


async def test_write_batch_ceiling_is_accepted_with_chunked_history_reads() -> None:
    facts = [
        _fact(
            source_record_id=f"PRICE-BOUNDARY-{index:03d}",
            status=MarketPriceSourceFactStatus.RETIRED,
        )
        for index in range(MAX_MARKET_PRICE_SOURCE_FACT_WRITE_BATCH)
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([]))
    db.scalars = AsyncMock(return_value=_result([]))
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    changes = await MarketPriceSourceFactWriter(db).append_many(facts)

    assert len(changes) == MAX_MARKET_PRICE_SOURCE_FACT_WRITE_BATCH
    assert db.execute.await_count == MAX_MARKET_PRICE_SOURCE_FACT_WRITE_BATCH + 2
    assert db.scalars.await_count == 10
    db.add_all.assert_called_once()
    assert len(db.add_all.call_args.args[0]) == MAX_MARKET_PRICE_SOURCE_FACT_WRITE_BATCH


async def test_write_batch_above_ceiling_fails_before_locking() -> None:
    fact = _fact(status=MarketPriceSourceFactStatus.RETIRED)
    db = _db(
        incoming_history=[],
        candidate_sources=[],
        candidate_history=[],
    )

    with pytest.raises(
        MarketPriceSourceFactError,
        match="write batch exceeds 500",
    ):
        await MarketPriceSourceFactWriter(db).append_many(
            [fact] * (MAX_MARKET_PRICE_SOURCE_FACT_WRITE_BATCH + 1)
        )

    db.execute.assert_not_awaited()
