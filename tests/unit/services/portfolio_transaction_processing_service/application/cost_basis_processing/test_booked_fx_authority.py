"""Separate public booked-rate admission from mutable effective-dated references."""

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.events import TransactionEvent
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.transaction_model_dto import Transaction
from src.services.portfolio_transaction_processing_service.app.application import (
    cost_basis_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisProcessingCheckpoint,
    EffectiveFxRate,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    transaction_mapping,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisAverageCostPoolPort,
    CostBasisFxRatePort,
    CostBasisLotStatePort,
    CostBasisProcessingStatePort,
    CostBasisTransactionStatePort,
)


def _public_buy(rate: str | None) -> Transaction:
    return Transaction(
        transaction_id="BOOKED-FX-AUTHORITY-BUY",
        portfolio_id="BOOKED-FX-AUTHORITY-PORTFOLIO",
        instrument_id="BOOKED-FX-AUTHORITY-EQUITY",
        security_id="BOOKED-FX-AUTHORITY-EQUITY",
        transaction_date="2026-04-09T10:00:00Z",
        transaction_type="BUY",
        quantity="10",
        price="100",
        gross_transaction_amount="1000",
        trade_currency="XTS",
        currency="XTS",
        transaction_fx_rate=rate,
    )


@pytest.mark.parametrize("rate", ["0", "-2", "NaN", "Infinity", "-Infinity"])
def test_public_booked_fx_rejects_nonpositive_and_nonfinite_rates(rate: str) -> None:
    with pytest.raises(ValidationError) as raised:
        _public_buy(rate)

    assert any(error["loc"] == ("transaction_fx_rate",) for error in raised.value.errors())


@pytest.mark.asyncio
async def test_mixed_booked_and_derived_fx_keep_distinct_authority_after_reference_correction():
    """New/replayed inputs use the same rule; later facts cannot price an earlier trade."""
    booked = _public_buy("2").model_dump()
    booked["transaction_fx_rate_origin"] = "SOURCE_BOOKED"
    absent = _public_buy(None).model_dump()
    absent["transaction_id"] = "REFERENCE-DERIVED-BUY"
    absent["transaction_fx_rate_origin"] = None
    earlier = deepcopy(absent)
    earlier["transaction_id"] = "EARLIER-REFERENCE-DERIVED-BUY"
    earlier["transaction_date"] = "2026-04-08T10:00:00Z"
    # Deliberately nonchronological input order, as on incremental/backdated delivery.
    source = [absent, booked, earlier]
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.return_value = [
        EffectiveFxRate(effective_date=date(2026, 4, 8), rate=Decimal("1.5")),
        EffectiveFxRate(effective_date=date(2026, 4, 9), rate=Decimal("2.5")),
        EffectiveFxRate(effective_date=date(2026, 4, 10), rate=Decimal("9")),
    ]

    initial = await cost_basis_processing.enrich_cost_basis_transactions_with_fx(
        transactions=deepcopy(source), portfolio_base_currency="USD", fx_rates=fx_rates
    )
    assert [row["transaction_fx_rate"] for row in initial] == [
        Decimal("2.5"),
        Decimal("2"),
        Decimal("1.5"),
    ]
    assert [row["transaction_fx_rate_origin"] for row in initial] == [
        "REFERENCE_DERIVED",
        "SOURCE_BOOKED",
        "REFERENCE_DERIVED",
    ]
    fx_rates.get_fx_rate_window.assert_awaited_once_with(
        from_currency="XTS",
        to_currency="USD",
        start_date=date(2026, 4, 8),
        end_date=date(2026, 4, 9),
    )

    # A corrected reference is visible only to a new derivation, not booked cost authority.
    fx_rates.get_fx_rate_window.return_value[1] = EffectiveFxRate(
        effective_date=date(2026, 4, 9), rate=Decimal("3")
    )
    replayed = await cost_basis_processing.enrich_cost_basis_transactions_with_fx(
        transactions=deepcopy(source), portfolio_base_currency="USD", fx_rates=fx_rates
    )
    assert [row["transaction_fx_rate"] for row in replayed] == [
        Decimal("3"),
        Decimal("2"),
        Decimal("1.5"),
    ]
    assert [row["transaction_fx_rate_origin"] for row in replayed] == [
        "REFERENCE_DERIVED",
        "SOURCE_BOOKED",
        "REFERENCE_DERIVED",
    ]
    assert source[0]["transaction_fx_rate"] is None
    assert source[1]["transaction_fx_rate"] == Decimal("2")
    # Independent implications of admitted inputs, not a calculator/persistence claim.
    assert Decimal("1000") * replayed[1]["transaction_fx_rate"] == Decimal("2000")
    assert Decimal("1100") * Decimal("2.5") - Decimal("2000") == Decimal("750")


@pytest.mark.asyncio
@pytest.mark.parametrize("incremental", [False, True], ids=["full-rebuild", "ordered-append"])
async def test_actual_cost_coordinator_preserves_booked_fx_and_lineage_version(incremental):
    """Exercise both real calculator modes, with state ports isolated from PostgreSQL."""
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)
    transactions.get_transaction_history.return_value = []
    state = AsyncMock(spec=CostBasisProcessingStatePort)
    state.get_cost_basis_processing_checkpoint.return_value = None
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.return_value = [
        EffectiveFxRate(effective_date=date(2026, 4, 9), rate=Decimal("2.5"))
    ]
    coordinator = cost_basis_processing.CostBasisCalculationCoordinator(
        transactions=transactions,
        average_cost_pools=AsyncMock(spec=CostBasisAverageCostPoolPort),
        lot_states=AsyncMock(spec=CostBasisLotStatePort),
        fx_rates=fx_rates,
        processing_state=state,
    )
    event = TransactionEvent(
        **_public_buy("2").model_dump(),
        tenant_id="synthetic-fx-authority",
        transaction_fx_rate_origin="SOURCE_BOOKED",
    )
    original = transaction_mapping.booked_transaction.to_booked_transaction(event)
    initial = await coordinator.calculate(
        transaction=original,
        transaction_type="BUY",
        portfolio_base_currency="USD",
        instrument=None,
        cost_basis_method=CostBasisMethod.FIFO,
    )
    assert initial.errored == []
    if incremental:
        state.get_cost_basis_processing_checkpoint.return_value = (
            CostBasisProcessingCheckpoint.from_transaction(
                initial.processed[0], cost_basis_method=CostBasisMethod.FIFO
            )
        )
    next_event = event.model_copy(
        update={
            "transaction_id": "BOOKED-FX-AUTHORITY-NEXT-BUY",
            "transaction_date": datetime(2026, 4, 10, 10, tzinfo=timezone.utc),
        }
    )
    result = await coordinator.calculate(
        transaction=transaction_mapping.booked_transaction.to_booked_transaction(next_event),
        transaction_type="BUY",
        portfolio_base_currency="USD",
        instrument=None,
        cost_basis_method=CostBasisMethod.FIFO,
        preloaded_transaction_history=[original] if not incremental else None,
    )
    assert result.incremental is incremental
    assert result.errored == []
    output = next(
        row for row in result.processed if row.transaction_id == next_event.transaction_id
    )
    assert output.transaction_fx_rate == Decimal("2")
    assert output.net_cost_local == Decimal("1000")
    assert output.net_cost == Decimal("2000")
    assert result.open_lot_states[next_event.transaction_id].cost_base == Decimal("2000")
    assert output.calculation_lineage.algorithm_id == "transaction-cost-basis-calculation"
    assert output.calculation_lineage.algorithm_version == 2
    fx_rates.get_fx_rate_window.assert_not_awaited()


@pytest.mark.asyncio
async def test_actual_fifo_disposal_uses_booked_fx_and_trade_currency_fee():
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)
    state = AsyncMock(spec=CostBasisProcessingStatePort)
    state.get_cost_basis_processing_checkpoint.return_value = None
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    coordinator = cost_basis_processing.CostBasisCalculationCoordinator(
        transactions=transactions,
        average_cost_pools=AsyncMock(spec=CostBasisAverageCostPoolPort),
        lot_states=AsyncMock(spec=CostBasisLotStatePort),
        fx_rates=fx_rates,
        processing_state=state,
    )
    original = TransactionEvent(
        **_public_buy("2").model_dump(),
        tenant_id="synthetic-fx-authority",
        transaction_fx_rate_origin="SOURCE_BOOKED",
    )
    sale = original.model_copy(
        update={
            "transaction_id": "BOOKED-FX-FEE-SELL",
            "transaction_type": "SELL",
            "transaction_date": datetime(2026, 4, 9, 16, tzinfo=timezone.utc),
            "quantity": Decimal("5"),
            "price": Decimal("110"),
            "gross_transaction_amount": Decimal("550"),
            "trade_fee": Decimal("2"),
        }
    )
    result = await coordinator.calculate(
        transaction=transaction_mapping.booked_transaction.to_booked_transaction(sale),
        transaction_type="SELL",
        portfolio_base_currency="USD",
        instrument=None,
        cost_basis_method=CostBasisMethod.FIFO,
        preloaded_transaction_history=[
            transaction_mapping.booked_transaction.to_booked_transaction(original)
        ],
    )
    assert result.errored == []
    output = next(row for row in result.processed if row.transaction_id == sale.transaction_id)
    assert output.realized_gain_loss_local == Decimal("48")
    assert output.realized_gain_loss == Decimal("96")
    fx_rates.get_fx_rate_window.assert_not_awaited()
