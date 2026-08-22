"""Verify prepared cost-processing execution across calculation and FX routes."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    CostProcessingRoute,
    OpenLotPersistenceScope,
    PreparedCostProcessingUseCase,
    PreparedCostTransaction,
)
from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    execution as execution_module,
)
from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing.persistence_scope import (  # noqa: E501
    CostBasisTransactionPersistenceScope,
)
from src.services.portfolio_transaction_processing_service.app.application.errors import (
    TransactionProcessingRejected,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostCalculationError,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    redemption as redemption_domain,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    FxContractInstrument,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    AccruedIncomeOffsetStatePort,
    CorporateActionReconciliationRepository,
    CostBasisAverageCostPoolPort,
    CostBasisFxRatePort,
    CostBasisInstrumentReference,
    CostBasisLotBasisTransferPort,
    CostBasisLotDisposalPort,
    CostBasisLotStatePort,
    CostBasisPortfolioReference,
    CostBasisProcessingStatePort,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
    CostProcessingResult,
    InitialOpeningCostStatePort,
    LotAmortizedCostProfilePort,
)

RedemptionLinkedEventValidationError = redemption_domain.RedemptionLinkedEventValidationError
RedemptionLinkedEventValidationReasonCode = (
    redemption_domain.RedemptionLinkedEventValidationReasonCode
)


def _transaction(*, transaction_type: str = "BUY") -> BookedTransaction:
    return BookedTransaction(
        transaction_id=f"{transaction_type}-EXECUTION-01",
        portfolio_id="PORT-COST-01",
        instrument_id="INSTRUMENT-01",
        security_id="SECURITY-01",
        transaction_date=datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=Decimal("10"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("250"),
        trade_currency="SGD",
        currency="SGD",
        epoch=7,
    )


def _prepared(*, route: CostProcessingRoute) -> PreparedCostTransaction:
    transaction_type = "FX_SPOT" if route is CostProcessingRoute.FOREIGN_EXCHANGE else "BUY"
    return PreparedCostTransaction(
        transaction=_transaction(transaction_type=transaction_type),
        transaction_type=transaction_type,
        cost_basis_method=CostBasisMethod.FIFO,
        route=route,
    )


def _dependencies() -> dict[str, object]:
    return {
        "portfolio": CostBasisPortfolioReference(
            portfolio_id="PORT-COST-01",
            base_currency="SGD",
            cost_basis_method=CostBasisMethod.FIFO,
        ),
        "instrument": CostBasisInstrumentReference(
            security_id="SECURITY-01",
            product_type="EQUITY",
            asset_class="EQUITY",
        ),
        "transaction_state": AsyncMock(spec=CostBasisTransactionStatePort),
        "average_cost_pools": AsyncMock(spec=CostBasisAverageCostPoolPort),
        "lot_disposals": AsyncMock(spec=CostBasisLotDisposalPort),
        "lot_basis_transfers": AsyncMock(spec=CostBasisLotBasisTransferPort),
        "lot_states": AsyncMock(spec=CostBasisLotStatePort),
        "amortized_cost_profiles": AsyncMock(spec=LotAmortizedCostProfilePort),
        "income_offsets": AsyncMock(spec=AccruedIncomeOffsetStatePort),
        "initial_opening_state": AsyncMock(spec=InitialOpeningCostStatePort),
        "fx_rates": AsyncMock(spec=CostBasisFxRatePort),
        "processing_state": AsyncMock(spec=CostBasisProcessingStatePort),
        "reconciliation_repository": AsyncMock(spec=CorporateActionReconciliationRepository),
        "effect_stager": AsyncMock(spec=CostProcessingEffectStagingPort),
        "correlation_id": "corr-execution-01",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("incremental", "expected_persistence_scope"),
    [
        (True, CostBasisTransactionPersistenceScope.AFFECTED_SUFFIX),
        (False, CostBasisTransactionPersistenceScope.REBUILD_AUTHORITY),
    ],
)
async def test_cost_basis_execution_acquires_key_lock_before_calculation(
    monkeypatch: pytest.MonkeyPatch,
    incremental: bool,
    expected_persistence_scope: CostBasisTransactionPersistenceScope,
) -> None:
    prepared = _prepared(route=CostProcessingRoute.COST_BASIS)
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    calculation = MagicMock(
        processed=[],
        errored=[],
        open_lot_states={},
        incremental=incremental,
        open_lot_persistence_scope=MagicMock(),
        average_cost_pool_transition=None,
        disposals=(),
        basis_transfers=(),
        missing_economics_authority_transaction_ids=frozenset({"BUY-PRIOR"}),
    )
    coordinator = MagicMock()
    coordinator.return_value.calculate = AsyncMock(return_value=calculation)
    monkeypatch.setattr(execution_module, "CostBasisCalculationCoordinator", coordinator)
    apply_amortized_disposal = AsyncMock(return_value=calculation)
    monkeypatch.setattr(
        execution_module,
        "apply_effective_amortized_cost_to_disposals",
        apply_amortized_disposal,
    )
    persisted = (prepared.transaction,)
    persistence_order: list[str] = []
    persist_transactions = AsyncMock(
        side_effect=lambda **_kwargs: persistence_order.append("transactions") or persisted
    )
    monkeypatch.setattr(
        execution_module,
        "persist_cost_basis_transactions",
        persist_transactions,
    )
    monkeypatch.setattr(
        execution_module,
        "persist_open_lot_state",
        AsyncMock(side_effect=lambda **_kwargs: persistence_order.append("lot-state")),
    )
    persist_disposals = AsyncMock(
        side_effect=lambda **_kwargs: persistence_order.append("disposal-receipts")
    )
    monkeypatch.setattr(
        execution_module,
        "persist_current_lot_disposals",
        persist_disposals,
    )
    persist_basis_transfers = AsyncMock(
        side_effect=lambda **_kwargs: persistence_order.append("basis-transfer-receipts")
    )
    monkeypatch.setattr(
        execution_module,
        "persist_current_lot_basis_transfers",
        persist_basis_transfers,
    )
    monkeypatch.setattr(
        execution_module,
        "_persist_processing_checkpoint",
        AsyncMock(side_effect=lambda **_kwargs: persistence_order.append("checkpoint")),
    )

    amortized_cost_profiles = AsyncMock(spec=LotAmortizedCostProfilePort)
    result = await PreparedCostProcessingUseCase()._calculate_cost_basis(
        prepared=prepared,
        portfolio=CostBasisPortfolioReference(
            portfolio_id="PORT-COST-01",
            base_currency="SGD",
            cost_basis_method=CostBasisMethod.FIFO,
        ),
        instrument=CostBasisInstrumentReference(
            security_id="SECURITY-01",
            product_type="EQUITY",
            asset_class="EQUITY",
        ),
        transaction_state=transaction_state,
        average_cost_pools=AsyncMock(spec=CostBasisAverageCostPoolPort),
        lot_disposals=AsyncMock(spec=CostBasisLotDisposalPort),
        lot_basis_transfers=AsyncMock(spec=CostBasisLotBasisTransferPort),
        lot_states=AsyncMock(spec=CostBasisLotStatePort),
        amortized_cost_profiles=amortized_cost_profiles,
        income_offsets=AsyncMock(spec=AccruedIncomeOffsetStatePort),
        initial_opening_state=AsyncMock(spec=InitialOpeningCostStatePort),
        fx_rates=AsyncMock(spec=CostBasisFxRatePort),
        processing_state=processing_state,
    )

    assert result == persisted
    processing_state.acquire_cost_basis_processing_lock.assert_awaited_once_with(
        "PORT-COST-01",
        "SECURITY-01",
    )
    processing_state.acquire_linked_redemption_group_lock.assert_not_awaited()
    persist_disposals.assert_awaited_once()
    persist_basis_transfers.assert_awaited_once()
    apply_amortized_disposal.assert_awaited_once_with(
        calculation,
        portfolio=CostBasisPortfolioReference(
            portfolio_id="PORT-COST-01",
            base_currency="SGD",
            cost_basis_method=CostBasisMethod.FIFO,
        ),
        cost_basis_method=CostBasisMethod.FIFO,
        profiles=amortized_cost_profiles,
    )
    amortized_cost_profiles.effective_as_of_many.assert_not_awaited()
    assert persist_transactions.await_args.kwargs["persistence_scope"] is expected_persistence_scope
    assert persist_transactions.await_args.kwargs["missing_authority_transaction_ids"] == {
        "BUY-PRIOR"
    }
    assert persistence_order == [
        "transactions",
        "disposal-receipts",
        "basis-transfer-receipts",
        "lot-state",
        "checkpoint",
    ]


@pytest.mark.asyncio
async def test_non_buy_initial_opening_uses_generic_lot_and_checkpoint_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep transfers out of the BUY-only aggregate persistence optimization."""
    transaction = _transaction(transaction_type="TRANSFER_IN")
    prepared = PreparedCostTransaction(
        transaction=transaction,
        transaction_type="TRANSFER_IN",
        cost_basis_method=CostBasisMethod.FIFO,
        route=CostProcessingRoute.COST_BASIS,
    )
    calculation = MagicMock(
        processed=[transaction],
        errored=[],
        open_lot_states={},
        incremental=True,
        open_lot_persistence_scope=OpenLotPersistenceScope.INITIAL_OPENING_LOT,
        average_cost_pool_transition=None,
        disposals=(),
        basis_transfers=(),
    )
    coordinator = MagicMock()
    coordinator.return_value.calculate = AsyncMock(return_value=calculation)
    monkeypatch.setattr(execution_module, "CostBasisCalculationCoordinator", coordinator)
    monkeypatch.setattr(
        execution_module,
        "apply_effective_amortized_cost_to_disposals",
        AsyncMock(return_value=calculation),
    )
    persist_transactions = AsyncMock(return_value=(transaction,))
    persist_lot_state = AsyncMock()
    persist_checkpoint = AsyncMock()
    monkeypatch.setattr(
        execution_module,
        "persist_cost_basis_transactions",
        persist_transactions,
    )
    monkeypatch.setattr(execution_module, "persist_open_lot_state", persist_lot_state)
    monkeypatch.setattr(
        execution_module,
        "persist_current_lot_disposals",
        AsyncMock(),
    )
    monkeypatch.setattr(
        execution_module,
        "persist_current_lot_basis_transfers",
        AsyncMock(),
    )
    monkeypatch.setattr(
        execution_module,
        "_persist_processing_checkpoint",
        persist_checkpoint,
    )
    dependencies = _dependencies()

    result = await PreparedCostProcessingUseCase()._calculate_cost_basis(
        prepared=prepared,
        portfolio=dependencies["portfolio"],
        instrument=dependencies["instrument"],
        transaction_state=dependencies["transaction_state"],
        average_cost_pools=dependencies["average_cost_pools"],
        lot_disposals=dependencies["lot_disposals"],
        lot_basis_transfers=dependencies["lot_basis_transfers"],
        lot_states=dependencies["lot_states"],
        amortized_cost_profiles=dependencies["amortized_cost_profiles"],
        income_offsets=dependencies["income_offsets"],
        initial_opening_state=dependencies["initial_opening_state"],
        fx_rates=dependencies["fx_rates"],
        processing_state=dependencies["processing_state"],
    )

    assert result == (transaction,)
    assert persist_transactions.await_args.kwargs["initial_opening_checkpoint"] is None
    persist_lot_state.assert_awaited_once()
    assert (
        persist_lot_state.await_args.kwargs["persistence_scope"]
        is OpenLotPersistenceScope.INITIAL_OPENING_LOT
    )
    persist_checkpoint.assert_awaited_once()


@pytest.mark.asyncio
async def test_cost_basis_execution_rejects_linked_interest_before_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redemption = replace(
        _transaction(transaction_type="MATURITY_REDEMPTION"),
        linked_transaction_group_id="GROUP-REDEMPTION-01",
        accrued_interest_proceeds_local=Decimal("25"),
    )
    independent_interest = replace(
        _transaction(transaction_type="INTEREST"),
        transaction_id="INTEREST-EXECUTION-01",
        instrument_id="INTEREST-CASH-01",
        security_id="INTEREST-CASH-01",
        linked_transaction_group_id="GROUP-REDEMPTION-01",
    )
    prepared = PreparedCostTransaction(
        transaction=redemption,
        transaction_type="MATURITY_REDEMPTION",
        cost_basis_method=CostBasisMethod.FIFO,
        route=CostProcessingRoute.COST_BASIS,
    )
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    lock_order: list[str] = []
    processing_state.acquire_cost_basis_processing_lock.side_effect = lambda *_args: (
        lock_order.append("security-lock")
    )
    processing_state.acquire_linked_redemption_group_lock.side_effect = lambda *_args: (
        lock_order.append("group-lock")
    )
    transaction_state.get_linked_transaction_group.side_effect = lambda **_kwargs: (
        lock_order.append("group-read") or [independent_interest]
    )
    coordinator = MagicMock()
    monkeypatch.setattr(execution_module, "CostBasisCalculationCoordinator", coordinator)

    with pytest.raises(RedemptionLinkedEventValidationError) as raised:
        await PreparedCostProcessingUseCase()._calculate_cost_basis(
            prepared=prepared,
            portfolio=CostBasisPortfolioReference(
                portfolio_id="PORT-COST-01",
                base_currency="SGD",
                cost_basis_method=CostBasisMethod.FIFO,
            ),
            instrument=CostBasisInstrumentReference(
                security_id="SECURITY-01",
                product_type="FIXED_INCOME",
                asset_class="FIXED_INCOME",
            ),
            transaction_state=transaction_state,
            average_cost_pools=AsyncMock(spec=CostBasisAverageCostPoolPort),
            lot_disposals=AsyncMock(spec=CostBasisLotDisposalPort),
            lot_basis_transfers=AsyncMock(spec=CostBasisLotBasisTransferPort),
            lot_states=AsyncMock(spec=CostBasisLotStatePort),
            amortized_cost_profiles=AsyncMock(spec=LotAmortizedCostProfilePort),
            income_offsets=AsyncMock(spec=AccruedIncomeOffsetStatePort),
            initial_opening_state=AsyncMock(spec=InitialOpeningCostStatePort),
            fx_rates=AsyncMock(spec=CostBasisFxRatePort),
            processing_state=processing_state,
        )

    assert raised.value.reason_code is (
        RedemptionLinkedEventValidationReasonCode.DUPLICATE_ACCRUED_INTEREST
    )
    processing_state.acquire_cost_basis_processing_lock.assert_awaited_once_with(
        "PORT-COST-01",
        "SECURITY-01",
    )
    processing_state.acquire_linked_redemption_group_lock.assert_awaited_once_with(
        "PORT-COST-01",
        "GROUP-REDEMPTION-01",
    )
    assert lock_order == ["security-lock", "group-lock", "group-read"]
    transaction_state.get_linked_transaction_group.assert_awaited_once_with(
        portfolio_id="PORT-COST-01",
        linked_transaction_group_id="GROUP-REDEMPTION-01",
        exclude_id="MATURITY_REDEMPTION-EXECUTION-01",
    )
    transaction_state.get_transaction_history.assert_not_awaited()
    coordinator.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("incoming_is_redemption", [True, False])
async def test_linked_income_history_validation_is_symmetric(
    incoming_is_redemption: bool,
) -> None:
    redemption = replace(
        _transaction(transaction_type="MATURITY_REDEMPTION"),
        linked_transaction_group_id="GROUP-REDEMPTION-01",
        accrued_interest_proceeds_local=Decimal("25"),
    )
    interest = replace(
        _transaction(transaction_type="INTEREST"),
        instrument_id="INTEREST-CASH-01",
        security_id="INTEREST-CASH-01",
        linked_transaction_group_id="GROUP-REDEMPTION-01",
    )
    incoming, peer = (redemption, interest) if incoming_is_redemption else (interest, redemption)
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)
    transaction_state.get_linked_transaction_group.return_value = [peer]

    with pytest.raises(RedemptionLinkedEventValidationError):
        await execution_module._validate_linked_redemption_group(
            transaction=incoming,
            transaction_state=transaction_state,
        )

    transaction_state.get_linked_transaction_group.assert_awaited_once_with(
        portfolio_id=incoming.portfolio_id,
        linked_transaction_group_id="GROUP-REDEMPTION-01",
        exclude_id=incoming.transaction_id,
    )
    transaction_state.get_transaction_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_unrelated_transaction_does_not_read_linked_income_history() -> None:
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)

    result = await execution_module._validate_linked_redemption_group(
        transaction=_transaction(),
        transaction_state=transaction_state,
    )

    assert result is None
    transaction_state.get_linked_transaction_group.assert_not_awaited()
    transaction_state.get_transaction_history.assert_not_awaited()


def test_amortized_disposal_runtime_is_enabled_with_correction_replay() -> None:
    assert execution_module._AMORTIZED_DISPOSAL_RUNTIME_ENABLED is True


@pytest.mark.asyncio
async def test_execution_rejects_historical_calculation_error_before_persistence() -> None:
    with pytest.raises(
        ValueError,
        match="Cost-basis calculation failed for SELL-LATER: insufficient open quantity",
    ):
        execution_module._raise_for_calculation_errors(
            [
                CostCalculationError(
                    transaction_id="SELL-LATER",
                    error_reason="insufficient open quantity",
                )
            ]
        )


def test_execution_governs_quantity_restatement_rejection_without_leaking_detail() -> None:
    confidential_detail = "remainder 0.00000000001 for private transaction quantity"

    with pytest.raises(TransactionProcessingRejected) as exc_info:
        execution_module._raise_for_calculation_errors(
            [
                CostCalculationError(
                    transaction_id="SPLIT-REJECTED",
                    error_reason=(
                        "Quantity restatement invariant violation: " + confidential_detail
                    ),
                )
            ]
        )

    assert exc_info.value.reason_code == "lot_quantity_restatement_rejected"
    assert exc_info.value.retryable is False
    assert exc_info.value.detail == {
        "transaction_id": "SPLIT-REJECTED",
        "reason": "lot_restatement_invariant_violation",
    }
    assert confidential_detail not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [CostProcessingRoute.COST_BASIS, CostProcessingRoute.FOREIGN_EXCHANGE],
)
async def test_execution_routes_prepared_transaction_without_framework_events(
    route: CostProcessingRoute,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(route=route)
    use_case = PreparedCostProcessingUseCase()
    cost_result = (prepared.transaction,)
    fx_instrument = MagicMock(spec=FxContractInstrument)
    use_case._calculate_cost_basis = AsyncMock(return_value=cost_result)
    use_case._book_foreign_exchange = AsyncMock(return_value=(cost_result, (fx_instrument,)))
    expected = CostProcessingResult(
        processed_transactions=cost_result,
        instrument_update_count=(1 if route is CostProcessingRoute.FOREIGN_EXCHANGE else 0),
    )
    coordination = AsyncMock(return_value=expected)
    monkeypatch.setattr(execution_module, "coordinate_cost_processing_effects", coordination)
    dependencies = _dependencies()

    result = await use_case.execute(prepared=prepared, **dependencies)

    assert result == expected
    if route is CostProcessingRoute.FOREIGN_EXCHANGE:
        use_case._book_foreign_exchange.assert_awaited_once()
        use_case._calculate_cost_basis.assert_not_awaited()
    else:
        use_case._calculate_cost_basis.assert_awaited_once()
        use_case._book_foreign_exchange.assert_not_awaited()
    coordination.assert_awaited_once()
