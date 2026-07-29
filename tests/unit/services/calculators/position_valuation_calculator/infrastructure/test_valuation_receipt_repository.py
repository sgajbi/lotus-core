"""Tests for valuation receipt persistence and reconstruction."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    DailyPositionValuationReceiptRecord,
)
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    MarketPriceSourceFactStatus,
    ValuationAuthorityScope,
    ValuationSnapshotIdentity,
    build_authoritative_valuation_receipt,
    build_calculation_lineage,
    canonical_content_hash,
)
from portfolio_common.domain.valuation.numeric_policy import (
    POSITION_VALUATION_LEDGER_OUTPUT_V1,
)
from sqlalchemy.dialects import postgresql

from src.services.calculators.position_valuation_calculator.app.infrastructure import (
    SqlAlchemyValuationReceiptRepository,
)
from src.services.calculators.position_valuation_calculator.app.infrastructure import (
    valuation_receipt_repository as receipt_repository,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


def _source(record_id: str) -> FinancialSourceReference:
    return FinancialSourceReference(
        source_system="valuation-receipt-repository-test",
        source_record_id=record_id,
        source_revision="1",
        source_content_hash=canonical_content_hash({"record_id": record_id}),
        observed_at=datetime(2026, 7, 29, 11, tzinfo=UTC),
    )


def _receipt():
    price_fact = MarketPriceSourceFact(
        scope=ValuationAuthorityScope("TENANT-SG", "BOOK-SG", "BOND-001"),
        price_date=date(2026, 7, 29),
        price=Decimal("1013.5"),
        currency="USD",
        quote_basis=MarketPriceQuoteBasis.UNIT_PRICE,
        source_reference=_source("market-price"),
        fact_status=MarketPriceSourceFactStatus.ACTIVE,
        fact_version=2,
    )
    return build_authoritative_valuation_receipt(
        snapshot_identity=ValuationSnapshotIdentity(
            portfolio_id="PORT-001",
            security_id="BOND-001",
            valuation_date=date(2026, 7, 29),
            epoch=3,
        ),
        policy_id="UNIT_PRICE_MARKET_VALUE",
        policy_version=1,
        assignment_version=4,
        assignment_content_hash="b" * 64,
        policy_assignment_source=_source("policy-assignment"),
        price_fact=price_fact,
        calculation_lineage=build_calculation_lineage(
            algorithm_id="POSITION_VALUATION_SCALING",
            algorithm_version=2,
            intermediate_precision=64,
            input_payload={"price": Decimal("1013.5")},
            output_payload={"market_value": Decimal("10135")},
            numeric_output_policy=POSITION_VALUATION_LEDGER_OUTPUT_V1.lineage_identity(),
        ),
    )


def _record(snapshot_id: int = 17) -> DailyPositionValuationReceiptRecord:
    return DailyPositionValuationReceiptRecord(
        id=23,
        **receipt_repository._record_values(
            snapshot_id=snapshot_id,
            receipt=_receipt(),
        ),
    )


async def test_upsert_round_trips_complete_receipt_and_uses_snapshot_conflict_key() -> None:
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(one=lambda: _record())
    repository = SqlAlchemyValuationReceiptRepository(session)

    persisted = await repository.upsert(snapshot_id=17, receipt=_receipt())

    assert persisted == _receipt()
    statement = session.scalars.await_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )
    assert "ON CONFLICT (snapshot_id) DO UPDATE" in compiled
    assert "RETURNING daily_position_valuation_receipts" in compiled


async def test_fetch_many_deduplicates_ids_and_reconstructs_numeric_policy_lineage() -> None:
    session = AsyncMock()
    snapshot = DailyPositionSnapshot(
        id=17,
        portfolio_id="PORT-001",
        security_id="BOND-001",
        date=date(2026, 7, 29),
        epoch=3,
    )
    session.execute.return_value = SimpleNamespace(all=lambda: [(_record(), snapshot)])
    repository = SqlAlchemyValuationReceiptRepository(session)

    receipts = await repository.fetch_many([17, 17])

    assert receipts == {17: _receipt()}
    assert receipts[17].calculation_lineage is not None
    assert receipts[17].calculation_lineage.algorithm_id == "POSITION_VALUATION_SCALING"
    assert receipts[17].calculation_lineage.numeric_output_policy is not None
    assert (
        receipts[17].calculation_lineage.numeric_output_policy.policy_id
        == POSITION_VALUATION_LEDGER_OUTPUT_V1.lineage_identity().policy_id
    )
    session.execute.assert_awaited_once()


async def test_empty_fetch_and_invalid_ids_do_not_reach_database() -> None:
    session = AsyncMock()
    repository = SqlAlchemyValuationReceiptRepository(session)

    assert await repository.fetch_many([]) == {}
    with pytest.raises(ValueError, match="positive integers"):
        await repository.fetch_many([0])
    with pytest.raises(ValueError, match="positive integer"):
        await repository.upsert(snapshot_id=True, receipt=_receipt())
    with pytest.raises(ValueError, match="positive integer"):
        await repository.delete(snapshot_id=0)

    session.execute.assert_not_awaited()
    session.scalars.assert_not_awaited()


async def test_delete_targets_only_the_exact_snapshot_receipt() -> None:
    session = AsyncMock()
    repository = SqlAlchemyValuationReceiptRepository(session)

    await repository.delete(snapshot_id=17)

    statement = session.execute.await_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert compiled == (
        "DELETE FROM daily_position_valuation_receipts "
        "WHERE daily_position_valuation_receipts.snapshot_id = 17"
    )
