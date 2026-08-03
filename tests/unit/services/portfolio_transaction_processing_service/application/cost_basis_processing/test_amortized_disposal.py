"""Verify effective amortized carrying amounts overlay calculated SELL economics."""

from dataclasses import replace
from decimal import Decimal

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    CostBasisCalculationResult,
    OpenLotPersistenceScope,
    apply_effective_amortized_cost_to_disposals,
    build_cost_basis_timeline_processor,
)
from services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    lot_amortized_cost_profile_id,
    materialize_active_lot_amortized_cost_profile,
)
from services.portfolio_transaction_processing_service.app.ports import (
    CostBasisPortfolioReference,
)
from tests.test_support.fixed_income_book_cost import resolved_fixed_income_book_cost_inputs


class _EffectiveProfiles:
    def __init__(self) -> None:
        self.requests = ()

    async def effective_as_of_many(self, requests):
        self.requests = tuple(requests)
        base = materialize_active_lot_amortized_cost_profile(
            resolved_fixed_income_book_cost_inputs(),
            profile_version=1,
        )
        profiles = {}
        for request in self.requests:
            profile_id = lot_amortized_cost_profile_id(request.scope)
            profiles[request] = replace(
                base,
                scope=request.scope,
                profile_id=profile_id,
                periods=tuple(replace(period, profile_id=profile_id) for period in base.periods),
            )
        return profiles


def _raw_transaction(
    transaction_id: str,
    transaction_date: str,
    transaction_type: str,
    quantity: str,
    gross_amount: str,
) -> dict[str, object]:
    return {
        "transaction_id": transaction_id,
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "transaction_date": transaction_date,
        "transaction_type": transaction_type,
        "quantity": quantity,
        "price": "1",
        "gross_transaction_amount": gross_amount,
        "trade_currency": "SGD",
        "portfolio_base_currency": "SGD",
        "transaction_fx_rate": "1",
        "trade_fee": "0",
    }


@pytest.mark.asyncio
async def test_full_rebuild_overlays_sequential_partial_sells_and_lineage() -> None:
    timeline = build_cost_basis_timeline_processor().process_transactions(
        existing_transactions_raw=[],
        new_transactions_raw=[
            _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
            _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
            _raw_transaction("SELL_2", "2027-01-01T00:00:00Z", "SELL", "20", "35"),
        ],
    )
    calculation = CostBasisCalculationResult(
        processed=timeline.processed,
        errored=timeline.errored,
        open_lot_states=timeline.open_lot_states,
        incremental=False,
        open_lot_persistence_scope=OpenLotPersistenceScope.COMPLETE_SNAPSHOT,
        average_cost_pool_transition=None,
        disposals=timeline.disposals,
    )
    profiles = _EffectiveProfiles()

    decorated = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=CostBasisPortfolioReference(
            portfolio_id="P1",
            base_currency="SGD",
            cost_basis_method=CostBasisMethod.FIFO,
            tenant_id="TENANT_SG",
            legal_book_id="BOOK_SG_PB",
        ),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=profiles,  # type: ignore[arg-type]
    )

    assert len(profiles.requests) == 2
    first, second = decorated.disposals
    assert first.result.cost_local == Decimal("38.8000000000")
    assert second.result.cost_local == Decimal("20.0000000000")
    assert first.result.allocations[0].amortized_cost_evidence is not None
    second_evidence = second.result.allocations[0].amortized_cost_evidence
    assert second_evidence is not None
    assert second_evidence.open_quantity_before == Decimal("60.0000000000")
    assert second_evidence.residual_quantity == Decimal("40.0000000000")
    assert second_evidence.residual_cost_local == Decimal("40.0000000000")

    processed = {transaction.transaction_id: transaction for transaction in decorated.processed}
    assert processed["SELL_2"].net_cost_local == Decimal("-20.0000000000")
    assert processed["SELL_2"].realized_gain_loss_local == Decimal("15.0000000000")
    assert processed["SELL_2"].calculation_lineage.algorithm_id == (
        "fixed-income-amortized-cost-transaction-overlay"
    )
    assert decorated.open_lot_states == calculation.open_lot_states


@pytest.mark.asyncio
async def test_missing_accounting_scope_preserves_legacy_calculation_without_query() -> None:
    timeline = build_cost_basis_timeline_processor().process_transactions(
        existing_transactions_raw=[],
        new_transactions_raw=[
            _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
            _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
        ],
    )
    calculation = CostBasisCalculationResult(
        processed=timeline.processed,
        errored=timeline.errored,
        open_lot_states=timeline.open_lot_states,
        incremental=False,
        open_lot_persistence_scope=OpenLotPersistenceScope.COMPLETE_SNAPSHOT,
        average_cost_pool_transition=None,
        disposals=timeline.disposals,
    )
    profiles = _EffectiveProfiles()

    result = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=CostBasisPortfolioReference(
            portfolio_id="P1",
            base_currency="SGD",
            cost_basis_method=CostBasisMethod.FIFO,
        ),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=profiles,  # type: ignore[arg-type]
    )

    assert result is calculation
    assert profiles.requests == ()
