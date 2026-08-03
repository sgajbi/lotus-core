"""Verify prepared cost-processing execution across calculation and FX routes."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    CostProcessingRoute,
    PreparedCostProcessingUseCase,
    PreparedCostTransaction,
)
from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    execution as execution_module,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostCalculationError,
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
    CostBasisLotDisposalPort,
    CostBasisLotStatePort,
    CostBasisPortfolioReference,
    CostBasisProcessingStatePort,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
    CostProcessingResult,
    LotAmortizedCostProfilePort,
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
        "lot_states": AsyncMock(spec=CostBasisLotStatePort),
        "amortized_cost_profiles": AsyncMock(spec=LotAmortizedCostProfilePort),
        "income_offsets": AsyncMock(spec=AccruedIncomeOffsetStatePort),
        "fx_rates": AsyncMock(spec=CostBasisFxRatePort),
        "processing_state": AsyncMock(spec=CostBasisProcessingStatePort),
        "reconciliation_repository": AsyncMock(spec=CorporateActionReconciliationRepository),
        "effect_stager": AsyncMock(spec=CostProcessingEffectStagingPort),
        "correlation_id": "corr-execution-01",
    }


@pytest.mark.asyncio
async def test_cost_basis_execution_acquires_key_lock_before_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(route=CostProcessingRoute.COST_BASIS)
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    calculation = MagicMock(
        processed=[],
        errored=[],
        open_lot_states={},
        incremental=True,
        open_lot_persistence_scope=MagicMock(),
        average_cost_pool_transition=None,
        disposals=(),
    )
    coordinator = MagicMock()
    coordinator.return_value.calculate = AsyncMock(return_value=calculation)
    monkeypatch.setattr(execution_module, "CostBasisCalculationCoordinator", coordinator)
    persisted = (prepared.transaction,)
    persistence_order: list[str] = []
    monkeypatch.setattr(
        execution_module,
        "persist_cost_basis_transactions",
        AsyncMock(
            side_effect=lambda **_kwargs: persistence_order.append("transactions") or persisted
        ),
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
        lot_states=AsyncMock(spec=CostBasisLotStatePort),
        amortized_cost_profiles=amortized_cost_profiles,
        income_offsets=AsyncMock(spec=AccruedIncomeOffsetStatePort),
        fx_rates=AsyncMock(spec=CostBasisFxRatePort),
        processing_state=processing_state,
    )

    assert result == persisted
    processing_state.acquire_cost_basis_processing_lock.assert_awaited_once_with(
        "PORT-COST-01",
        "SECURITY-01",
    )
    persist_disposals.assert_awaited_once()
    amortized_cost_profiles.effective_as_of_many.assert_not_awaited()
    assert persistence_order == [
        "transactions",
        "disposal-receipts",
        "lot-state",
        "checkpoint",
    ]


def test_amortized_disposal_runtime_is_gated_pending_correction_replay() -> None:
    assert execution_module._AMORTIZED_DISPOSAL_RUNTIME_ENABLED is False


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
