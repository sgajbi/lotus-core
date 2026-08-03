"""Verify effective amortized carrying amounts overlay calculated SELL economics."""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

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


class _NoEffectiveProfiles(_EffectiveProfiles):
    async def effective_as_of_many(self, requests):
        self.requests = tuple(requests)
        return {}


class _FirstEffectiveProfileOnly(_EffectiveProfiles):
    async def effective_as_of_many(self, requests):
        profiles = await super().effective_as_of_many(requests)
        first_request = self.requests[0]
        return {first_request: profiles[first_request]}


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
    assert decorated.open_lot_states == calculation.open_lot_states


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
async def test_partial_profile_decision_preserves_unprofiled_disposal() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
        _raw_transaction("SELL_2", "2027-01-01T00:00:00Z", "SELL", "20", "35"),
    )

    result = await apply_effective_amortized_cost_to_disposals(
        calculation,
        portfolio=_accounting_portfolio(),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=_FirstEffectiveProfileOnly(),  # type: ignore[arg-type]
    )

    assert result.disposals[0].result.allocations[0].amortized_cost_evidence is not None
    assert result.disposals[1] == calculation.disposals[1]


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
async def test_non_sell_disposal_overlay_fails_closed() -> None:
    calculation = _calculation(
        _raw_transaction("BUY_1", "2026-01-01T00:00:00Z", "BUY", "100", "97"),
        _raw_transaction("SELL_1", "2026-06-30T00:00:00Z", "SELL", "40", "60"),
    )
    invalid = replace(
        calculation.disposals[0],
        disposal_transaction_id="BUY_1",
    )

    with pytest.raises(ValueError, match="currently supports SELL only"):
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
