"""Verify effective amortized carrying amounts overlay calculated SELL economics."""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    CostBasisCalculationResult,
    OpenLotPersistenceScope,
    apply_effective_amortized_cost_to_disposals,
    build_cost_basis_timeline_processor,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AmortizedCostCarryState,
    OpenLotState,
)
from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (  # noqa: E501
    AmortizedCostEligibilityReason,
    lot_amortized_cost_profile_id,
    materialize_active_lot_amortized_cost_profile,
    materialize_parked_lot_amortized_cost_profile,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisPortfolioReference,
)
from tests.test_support.fixed_income_book_cost import resolved_fixed_income_book_cost_inputs


class _EffectiveProfiles:
    def __init__(self) -> None:
        self.requests = ()
        self.calls = 0

    async def effective_as_of_many(self, requests):
        self.calls += 1
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


class _NoEffectiveProfiles(_EffectiveProfiles):
    async def effective_as_of_many(self, requests):
        self.requests = tuple(requests)
        return {}


class _FirstEffectiveProfileOnly(_EffectiveProfiles):
    async def effective_as_of_many(self, requests):
        profiles = await super().effective_as_of_many(requests)
        first_request = self.requests[0]
        return {first_request: profiles[first_request]}


class _ParkedProfiles(_EffectiveProfiles):
    async def effective_as_of_many(self, requests):
        self.calls += 1
        self.requests = tuple(requests)
        return {
            request: materialize_parked_lot_amortized_cost_profile(
                scope=request.scope,
                effective_date=request.effective_date,
                profile_version=2,
                reason=AmortizedCostEligibilityReason.ASSIGNMENT_MISSING,
            )
            for request in self.requests
        }


class _InvalidEffectiveProfile(_EffectiveProfiles):
    def __init__(self, invalid_field: str) -> None:
        super().__init__()
        self.invalid_field = invalid_field

    async def effective_as_of_many(self, requests):
        profiles = await super().effective_as_of_many(requests)
        request = self.requests[0]
        profile = profiles[request]
        if self.invalid_field == "scope":
            profile = replace(
                profile,
                scope=replace(profile.scope, tenant_id="OTHER_TENANT"),
            )
        else:
            profile = replace(profile, currency="USD")
        return {request: profile}


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


def _calculation(*transactions: dict[str, object]) -> CostBasisCalculationResult:
    timeline = build_cost_basis_timeline_processor().process_transactions(
        existing_transactions_raw=[],
        new_transactions_raw=list(transactions),
    )
    return CostBasisCalculationResult(
        processed=timeline.processed,
        errored=timeline.errored,
        open_lot_states=timeline.open_lot_states,
        incremental=False,
        open_lot_persistence_scope=OpenLotPersistenceScope.COMPLETE_SNAPSHOT,
        average_cost_pool_transition=None,
        disposals=timeline.disposals,
        source_transactions=timeline.source_transactions,
    )


def _accounting_portfolio():
    return CostBasisPortfolioReference(
        portfolio_id="P1",
        base_currency="SGD",
        cost_basis_method=CostBasisMethod.FIFO,
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
    )


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
        source_transactions=timeline.source_transactions,
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
    remaining_lot = decorated.open_lot_states["BUY_1"]
    assert remaining_lot.quantity == Decimal("40.0000000000")
    assert remaining_lot.cost_local == Decimal("38.8000000000")
    assert remaining_lot.cost_base == Decimal("38.8000000000")
    assert remaining_lot.amortized_cost is not None
    assert remaining_lot.amortized_cost.scheduled_cost_local == Decimal("100.0000000000")
    assert remaining_lot.amortized_cost.carrying_amount_local == Decimal("40.0000000000")
    assert remaining_lot.amortized_cost.carrying_amount_base == Decimal("40.0000000000")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transaction_type",
    ["MATURITY_REDEMPTION", "CALL_REDEMPTION", "PARTIAL_REDEMPTION"],
)
async def test_redemption_disposals_share_authoritative_book_cost_overlay(
    transaction_type: str,
) -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("DISPOSAL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
    )
    redemption = calculation.processed[-1].model_copy(update={"transaction_type": transaction_type})

    decorated = await apply_effective_amortized_cost_to_disposals(
        replace(calculation, processed=[*calculation.processed[:-1], redemption]),
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
    )

    processed = {transaction.transaction_id: transaction for transaction in decorated.processed}
    assert processed["DISPOSAL_1"].net_cost_local == Decimal("-38.8000000000")
    assert processed["DISPOSAL_1"].realized_gain_loss_local == Decimal("21.2000000000")
    assert decorated.disposals[0].result.allocations[0].amortized_cost_evidence is not None


@pytest.mark.asyncio
async def test_one_unit_partials_conserve_terminal_local_and_base_basis() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "3", "97"),
        _raw_transaction("SELL_1", "2026-06-28T00:00:00Z", "SELL", "1", "40"),
        _raw_transaction("SELL_2", "2026-06-29T00:00:00Z", "SELL", "1", "40"),
        _raw_transaction("SELL_3", "2026-06-30T00:00:00Z", "SELL", "1", "40"),
    )

    result = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
    )

    local_costs = tuple(disposal.result.cost_local for disposal in result.disposals)
    base_costs = tuple(disposal.result.cost_base for disposal in result.disposals)
    assert local_costs == (
        Decimal("32.3333333333"),
        Decimal("32.3333333333"),
        Decimal("32.3333333334"),
    )
    assert sum(local_costs, Decimal(0)) == Decimal("97.0000000000")
    assert sum(base_costs, Decimal(0)) == Decimal("97.0000000000")
    assert result.open_lot_states["BUY_1"].quantity == Decimal(0)
    assert result.open_lot_states["BUY_1"].amortized_cost is None


@pytest.mark.asyncio
async def test_large_disposal_stream_uses_one_bulk_profile_read_and_conserves_basis() -> None:
    disposal_count = 1001
    calculation = _calculation(
        _raw_transaction(
            "BUY_1",
            "2026-01-01T00:00:00Z",
            "BUY",
            str(disposal_count),
            "97",
        ),
        *(
            _raw_transaction(
                f"SELL_{ordinal:04d}",
                "2026-06-30T00:00:00Z",
                "SELL",
                "1",
                "1",
            )
            for ordinal in range(1, disposal_count + 1)
        ),
    )
    profiles = _EffectiveProfiles()

    result = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=profiles,  # type: ignore[arg-type]
    )

    assert profiles.calls == 1
    assert len(profiles.requests) == disposal_count
    assert sum(
        (disposal.result.cost_local for disposal in result.disposals),
        Decimal(0),
    ) == Decimal("97.0000000000")
    assert result.open_lot_states["BUY_1"].quantity == Decimal(0)


@pytest.mark.asyncio
async def test_incremental_sell_resolves_restored_source_lot_economics() -> None:
    restored_buy = _raw_transaction(
        "BUY_1",
        "2026-01-01T00:00:00Z",
        "BUY",
        "60",
        "58.2",
    )
    restored_buy["source_lot_order_quantity"] = Decimal("100")
    restored_buy["net_cost_local"] = "58.2"
    restored_buy["net_cost"] = "58.2"
    timeline = build_cost_basis_timeline_processor().process_increment(
        initial_open_lots_raw=[restored_buy],
        new_transactions_raw=[
            _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "20", "35")
        ],
    )
    calculation = CostBasisCalculationResult(
        processed=timeline.processed,
        errored=timeline.errored,
        open_lot_states=timeline.open_lot_states,
        incremental=True,
        open_lot_persistence_scope=OpenLotPersistenceScope.SELECTED_LOTS,
        average_cost_pool_transition=None,
        disposals=timeline.disposals,
        source_transactions=timeline.source_transactions,
    )

    decorated = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
    )

    evidence = decorated.disposals[0].result.allocations[0].amortized_cost_evidence
    assert evidence is not None
    assert evidence.original_quantity == Decimal("100")
    assert evidence.open_quantity_before == Decimal("60")
    assert evidence.consumed_quantity == Decimal("20")
    assert [transaction.transaction_id for transaction in decorated.processed] == ["SELL_1"]


@pytest.mark.asyncio
async def test_incremental_sell_uses_persisted_residual_and_original_book_fx() -> None:
    restored_buy = _raw_transaction(
        "BUY_1",
        "2026-01-01T00:00:00Z",
        "BUY",
        "2",
        "97",
    )
    restored_buy["source_lot_order_quantity"] = Decimal("3")
    restored_buy["net_cost_local"] = Decimal("70.0000000000")
    restored_buy["net_cost"] = Decimal("85.0000000000")
    restored_buy["amortized_cost_carry_state"] = AmortizedCostCarryState(
        profile_id="PROFILE-1",
        profile_version=1,
        profile_content_hash="a" * 64,
        recognized_through_date=resolved_fixed_income_book_cost_inputs().assignment.valid_from,
        scheduled_cost_local=Decimal("97.0000000000"),
        carrying_amount_local=Decimal("64.6666666667"),
        carrying_amount_base=Decimal("79.8353902264"),
        book_cost_fx_rate_to_base=Decimal("1.2345678912"),
    )
    timeline = build_cost_basis_timeline_processor().process_increment(
        initial_open_lots_raw=[restored_buy],
        new_transactions_raw=[
            _raw_transaction("SELL_2", "2026-06-30T00:00:00Z", "SELL", "1", "40")
        ],
    )
    calculation = CostBasisCalculationResult(
        processed=timeline.processed,
        errored=timeline.errored,
        open_lot_states=timeline.open_lot_states,
        incremental=True,
        open_lot_persistence_scope=OpenLotPersistenceScope.SELECTED_LOTS,
        average_cost_pool_transition=None,
        disposals=timeline.disposals,
        source_transactions=timeline.source_transactions,
    )

    result = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
    )

    evidence = result.disposals[0].result.allocations[0].amortized_cost_evidence
    assert evidence is not None
    assert evidence.book_cost_fx_rate_to_base == Decimal("1.2345678912")
    assert evidence.current_cost_base == Decimal("79.8353902264")
    assert evidence.residual_cost_local == Decimal("32.3333333334")
    assert evidence.residual_cost_base == Decimal("39.9176950776")
    assert evidence.consumed_cost_base + evidence.residual_cost_base == (evidence.current_cost_base)
    remaining_lot = result.open_lot_states["BUY_1"]
    assert remaining_lot.cost_local == Decimal("35.0000000000")
    assert remaining_lot.cost_base == Decimal("42.5000000000")
    assert remaining_lot.amortized_cost is not None
    assert remaining_lot.amortized_cost.carrying_amount_local == Decimal("32.3333333334")
    assert remaining_lot.amortized_cost.carrying_amount_base == Decimal("39.9176950776")


@pytest.mark.asyncio
async def test_incremental_carried_sell_without_effective_profile_fails_closed() -> None:
    restored_buy = _raw_transaction(
        "BUY_1",
        "2026-01-01T00:00:00Z",
        "BUY",
        "2",
        "97",
    )
    restored_buy["source_lot_order_quantity"] = Decimal("3")
    restored_buy["net_cost_local"] = Decimal("70.0000000000")
    restored_buy["net_cost"] = Decimal("85.0000000000")
    restored_buy["amortized_cost_carry_state"] = AmortizedCostCarryState(
        profile_id="PROFILE-1",
        profile_version=1,
        profile_content_hash="a" * 64,
        recognized_through_date=resolved_fixed_income_book_cost_inputs().assignment.valid_from,
        scheduled_cost_local=Decimal("97.0000000000"),
        carrying_amount_local=Decimal("64.6666666667"),
        carrying_amount_base=Decimal("79.8353902264"),
        book_cost_fx_rate_to_base=Decimal("1.2345678912"),
    )
    timeline = build_cost_basis_timeline_processor().process_increment(
        initial_open_lots_raw=[restored_buy],
        new_transactions_raw=[
            _raw_transaction("SELL_2", "2026-06-30T00:00:00Z", "SELL", "1", "40")
        ],
    )
    calculation = CostBasisCalculationResult(
        processed=timeline.processed,
        errored=timeline.errored,
        open_lot_states=timeline.open_lot_states,
        incremental=True,
        open_lot_persistence_scope=OpenLotPersistenceScope.SELECTED_LOTS,
        average_cost_pool_transition=None,
        disposals=timeline.disposals,
        source_transactions=timeline.source_transactions,
    )

    with pytest.raises(ValueError, match="profile gap follows persisted carry state"):
        await apply_effective_amortized_cost_to_disposals(
            calculation,
            portfolio=_accounting_portfolio(),
            cost_basis_method=CostBasisMethod.FIFO,
            profiles=_NoEffectiveProfiles(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_parked_profile_explicitly_unwinds_persisted_book_carry() -> None:
    restored_buy = _raw_transaction(
        "BUY_1",
        "2026-01-01T00:00:00Z",
        "BUY",
        "2",
        "70",
    )
    restored_buy["source_lot_order_quantity"] = Decimal("3")
    restored_buy["net_cost_local"] = Decimal("70.0000000000")
    restored_buy["net_cost"] = Decimal("85.0000000000")
    restored_buy["amortized_cost_carry_state"] = AmortizedCostCarryState(
        profile_id="PROFILE-1",
        profile_version=1,
        profile_content_hash="a" * 64,
        recognized_through_date=resolved_fixed_income_book_cost_inputs().assignment.valid_from,
        scheduled_cost_local=Decimal("97.0000000000"),
        carrying_amount_local=Decimal("64.6666666667"),
        carrying_amount_base=Decimal("79.8353902264"),
        book_cost_fx_rate_to_base=Decimal("1.2345678912"),
    )
    timeline = build_cost_basis_timeline_processor().process_increment(
        initial_open_lots_raw=[restored_buy],
        new_transactions_raw=[
            _raw_transaction("SELL_2", "2026-07-01T00:00:00Z", "SELL", "1", "40")
        ],
    )
    calculation = CostBasisCalculationResult(
        processed=timeline.processed,
        errored=timeline.errored,
        open_lot_states=timeline.open_lot_states,
        incremental=True,
        open_lot_persistence_scope=OpenLotPersistenceScope.SELECTED_LOTS,
        average_cost_pool_transition=None,
        disposals=timeline.disposals,
        source_transactions=timeline.source_transactions,
    )

    result = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=_ParkedProfiles(),  # type: ignore[arg-type]
    )

    disposal = result.disposals[0]
    assert disposal.result.cost_local == calculation.disposals[0].result.cost_local
    assert disposal.result.cost_base == calculation.disposals[0].result.cost_base
    assert disposal.result.allocations[0].amortized_cost_evidence is None
    assert result.open_lot_states["BUY_1"].amortized_cost is None


@pytest.mark.asyncio
async def test_basis_only_lot_change_preserves_independent_book_carry() -> None:
    restored_buy = _raw_transaction(
        "BUY_1",
        "2026-01-01T00:00:00Z",
        "BUY",
        "2",
        "97",
    )
    restored_buy["net_cost_local"] = Decimal("70")
    restored_buy["net_cost"] = Decimal("85")
    carry = AmortizedCostCarryState(
        profile_id="PROFILE-1",
        profile_version=1,
        profile_content_hash="a" * 64,
        recognized_through_date=resolved_fixed_income_book_cost_inputs().assignment.valid_from,
        scheduled_cost_local=Decimal("97.0000000000"),
        carrying_amount_local=Decimal("64.6666666667"),
        carrying_amount_base=Decimal("79.8353902264"),
        book_cost_fx_rate_to_base=Decimal("1.2345678912"),
    )
    restored_buy["amortized_cost_carry_state"] = carry
    timeline = build_cost_basis_timeline_processor().process_increment(
        initial_open_lots_raw=[restored_buy],
        new_transactions_raw=[],
    )
    calculation = CostBasisCalculationResult(
        processed=timeline.processed,
        errored=timeline.errored,
        open_lot_states={
            "BUY_1": OpenLotState(
                original_quantity=Decimal("4"),
                quantity=Decimal("2"),
                cost_local=Decimal("50"),
                cost_base=Decimal("60"),
            )
        },
        incremental=True,
        open_lot_persistence_scope=OpenLotPersistenceScope.SELECTED_LOTS,
        average_cost_pool_transition=None,
        disposals=timeline.disposals,
        source_transactions=timeline.source_transactions,
    )

    result = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=_NoEffectiveProfiles(),  # type: ignore[arg-type]
    )

    assert result.open_lot_states["BUY_1"] == OpenLotState(
        original_quantity=Decimal("4"),
        quantity=Decimal("2"),
        cost_local=Decimal("50"),
        cost_base=Decimal("60"),
        amortized_cost=carry,
    )


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
        source_transactions=timeline.source_transactions,
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


@pytest.mark.asyncio
async def test_no_disposals_preserve_calculation_without_profile_query() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97")
    )
    profiles = _EffectiveProfiles()

    result = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=profiles,  # type: ignore[arg-type]
    )

    assert result is calculation
    assert profiles.requests == ()


@pytest.mark.asyncio
async def test_incomplete_accounting_scope_fails_closed() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
    )

    with pytest.raises(ValueError, match="accounting scope is incomplete"):
        await apply_effective_amortized_cost_to_disposals(
            calculation,
            portfolio=SimpleNamespace(
                tenant_id="TENANT_SG",
                legal_book_id=None,
            ),  # type: ignore[arg-type]
            cost_basis_method=CostBasisMethod.FIFO,
            profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_no_effective_profile_preserves_legacy_calculation() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
    )
    profiles = _NoEffectiveProfiles()

    result = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=profiles,  # type: ignore[arg-type]
    )

    assert result is calculation
    assert len(profiles.requests) == 1


@pytest.mark.asyncio
async def test_active_lot_profile_fails_closed_for_avco() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
    )

    with pytest.raises(ValueError, match="requires FIFO source-lot identity"):
        await apply_effective_amortized_cost_to_disposals(
            calculation,
            portfolio=_accounting_portfolio(),
            cost_basis_method=CostBasisMethod.AVCO,
            profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_profile_gap_after_amortized_partial_fails_closed() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
        _raw_transaction("SELL_2", "2027-01-01T00:00:00Z", "SELL", "20", "35"),
    )
    original_open_lot_states = dict(calculation.open_lot_states)

    with pytest.raises(ValueError, match="profile gap follows persisted carry state"):
        await apply_effective_amortized_cost_to_disposals(
            calculation,
            portfolio=_accounting_portfolio(),
            cost_basis_method=CostBasisMethod.FIFO,
            profiles=_FirstEffectiveProfileOnly(),  # type: ignore[arg-type]
        )
    assert calculation.open_lot_states == original_open_lot_states


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("invalid_field", "message"),
    [
        ("scope", "does not match requested lot scope"),
        ("currency", "currency does not match source-lot currency"),
    ],
)
async def test_invalid_effective_profile_fails_closed(
    invalid_field: str,
    message: str,
) -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
    )

    with pytest.raises(ValueError, match=message):
        await apply_effective_amortized_cost_to_disposals(
            calculation,
            portfolio=_accounting_portfolio(),
            cost_basis_method=CostBasisMethod.FIFO,
            profiles=_InvalidEffectiveProfile(invalid_field),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transaction_update", "message"),
    [
        ({"net_cost_local": None}, "missing positive local/base book cost"),
        ({"calculation_lineage": None}, "missing transaction calculation lineage"),
        ({"realized_gain_loss_local": None}, "missing realized_gain_loss_local"),
    ],
)
async def test_incomplete_calculated_sell_fails_closed(
    transaction_update: dict[str, object],
    message: str,
) -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
    )
    target_id = "BUY_1" if "net_cost_local" in transaction_update else "SELL_1"
    processed = [
        transaction.model_copy(update=transaction_update)
        if transaction.transaction_id == target_id
        else transaction
        for transaction in calculation.processed
    ]

    with pytest.raises(ValueError, match=message):
        await apply_effective_amortized_cost_to_disposals(
            replace(calculation, processed=processed),
            portfolio=_accounting_portfolio(),
            cost_basis_method=CostBasisMethod.FIFO,
            profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_missing_disposal_transaction_fails_closed() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
    )
    missing = replace(
        calculation.disposals[0],
        disposal_transaction_id="MISSING_TRANSACTION",
    )

    with pytest.raises(ValueError, match="missing transaction MISSING_TRANSACTION"):
        await apply_effective_amortized_cost_to_disposals(
            replace(calculation, disposals=(missing,)),
            portfolio=_accounting_portfolio(),
            cost_basis_method=CostBasisMethod.FIFO,
            profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_naive_booking_timestamp_fails_closed() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00", "SELL", "40", "60"),
    )
    processed = [
        transaction.model_copy(
            update={"transaction_date": transaction.transaction_date.replace(tzinfo=None)}
        )
        if transaction.transaction_id == "SELL_1"
        else transaction
        for transaction in calculation.processed
    ]
    with pytest.raises(ValueError, match="timezone-aware transaction timestamp"):
        await apply_effective_amortized_cost_to_disposals(
            replace(calculation, processed=processed),
            portfolio=_accounting_portfolio(),
            cost_basis_method=CostBasisMethod.FIFO,
            profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_disposal_without_open_source_lot_fails_closed() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
    )
    disposal = calculation.disposals[0]
    allocation = replace(
        disposal.result.allocations[0],
        source_transaction_id="SELL_1",
    )
    invalid = replace(
        disposal,
        result=replace(disposal.result, allocations=(allocation,)),
    )

    with pytest.raises(ValueError, match="cannot resolve pre-disposal source-lot quantity"):
        await apply_effective_amortized_cost_to_disposals(
            replace(calculation, disposals=(invalid,)),
            portfolio=_accounting_portfolio(),
            cost_basis_method=CostBasisMethod.FIFO,
            profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_non_governed_disposal_overlay_fails_closed() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
    )
    invalid = replace(
        calculation.disposals[0],
        disposal_transaction_id="BUY_1",
    )

    with pytest.raises(ValueError, match="requires a governed fixed-income disposal"):
        await apply_effective_amortized_cost_to_disposals(
            replace(calculation, disposals=(invalid,)),
            portfolio=_accounting_portfolio(),
            cost_basis_method=CostBasisMethod.FIFO,
            profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_amortized_overlay_updates_extended_realized_pnl_fields() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2027-01-01T00:00:00Z", "SELL", "40", "60"),
    )
    extended_pnl = {
        "realized_capital_pnl_local": Decimal("21.2"),
        "realized_total_pnl_local": Decimal("21.2"),
        "realized_capital_pnl_base": Decimal("21.2"),
        "realized_total_pnl_base": Decimal("21.2"),
    }
    processed = [
        transaction.model_copy(update=extended_pnl)
        if transaction.transaction_id == "SELL_1"
        else transaction
        for transaction in calculation.processed
    ]

    result = await apply_effective_amortized_cost_to_disposals(
        replace(calculation, processed=processed),
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=_EffectiveProfiles(),  # type: ignore[arg-type]
    )

    sell = next(item for item in result.processed if item.transaction_id == "SELL_1")
    assert sell.realized_capital_pnl_local == Decimal("20.0000000000")
    assert sell.realized_total_pnl_local == Decimal("20.0000000000")
    assert sell.realized_capital_pnl_base == Decimal("20.0000000000")
    assert sell.realized_total_pnl_base == Decimal("20.0000000000")
