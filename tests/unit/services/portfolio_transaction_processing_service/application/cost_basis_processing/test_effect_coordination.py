"""Verify domain-valued settlement, reconciliation, and effect staging coordination."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.infrastructure.persistence.transaction_identity_guard import (
    GeneratedTransactionIdentityCollisionError,
)

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    coordinate_cost_processing_effects,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.transaction import redemption
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    FxContractInstrument,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CorporateActionReconciliationRepository,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
)


def _transaction(
    *,
    transaction_id: str,
    transaction_type: str,
    net_cost_local: str = "25",
    epoch: int | None = None,
    auto_generate_cash_leg: bool = False,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT-COST-01",
        instrument_id="INSTRUMENT-01",
        security_id="SECURITY-01",
        transaction_date=datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=abs(Decimal(net_cost_local)),
        trade_currency="SGD",
        currency="SGD",
        net_cost_local=Decimal(net_cost_local),
        epoch=epoch,
        cash_entry_mode=("AUTO_GENERATE" if auto_generate_cash_leg else None),
        settlement_cash_account_id=("CASH-SGD-01" if auto_generate_cash_leg else None),
        settlement_cash_instrument_id=("CASH-SGD" if auto_generate_cash_leg else None),
    )


@pytest.mark.asyncio
async def test_effect_coordination_links_and_stages_generated_cash_leg() -> None:
    product_leg = _transaction(
        transaction_id="DIV-GENERATED-01",
        transaction_type="DIVIDEND",
        auto_generate_cash_leg=True,
    )
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)
    effect_stager = AsyncMock(spec=CostProcessingEffectStagingPort)

    result = await coordinate_cost_processing_effects(
        tenant_id="tenant-a",
        processed_transactions=[product_leg],
        instrument_updates=[],
        source_epoch=7,
        transaction_state=transaction_state,
        reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
        effect_stager=effect_stager,
        correlation_id="corr-generated-01",
    )

    assert [item.transaction_id for item in result.processed_transactions] == [
        "DIV-GENERATED-01",
        "DIV-GENERATED-01-CASHLEG",
    ]
    linked_product, generated_cash = result.processed_transactions
    assert linked_product.external_cash_transaction_id == "DIV-GENERATED-01-CASHLEG"
    assert generated_cash.transaction_type == "ADJUSTMENT"
    assert generated_cash.gross_transaction_amount == Decimal("25")
    assert generated_cash.movement_direction == "INFLOW"
    assert generated_cash.originating_transaction_id == "DIV-GENERATED-01"
    assert {item.epoch for item in result.processed_transactions} == {7}
    assert (
        transaction_state.upsert_generated_booked_transaction.await_args.args[0].transaction_id
        == "DIV-GENERATED-01-CASHLEG"
    )
    assert (
        transaction_state.upsert_booked_transaction.await_args.args[0].transaction_id
        == "DIV-GENERATED-01"
    )
    effect_stager.stage_processed_transactions.assert_awaited_once_with(
        result.processed_transactions,
        correlation_id="corr-generated-01",
    )


@pytest.mark.asyncio
async def test_effect_coordination_emits_separate_redemption_interest_income() -> None:
    product_leg = replace(
        _transaction(
            transaction_id="REDEMPTION-INTEREST-01",
            transaction_type="MATURITY_REDEMPTION",
            net_cost_local="100",
            auto_generate_cash_leg=True,
        ),
        quantity=Decimal("1"),
        price=Decimal("100"),
        principal_proceeds_local=Decimal("100"),
        accrued_interest_proceeds_local=Decimal("5"),
    )
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)

    result = await coordinate_cost_processing_effects(
        tenant_id="tenant-a",
        processed_transactions=[product_leg],
        instrument_updates=[],
        source_epoch=4,
        transaction_state=transaction_state,
        reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
        effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
        correlation_id="corr-redemption-interest-01",
    )

    assert [item.transaction_id for item in result.processed_transactions] == [
        "REDEMPTION-INTEREST-01",
        "REDEMPTION-INTEREST-01-ACCRUED-INTEREST",
        "REDEMPTION-INTEREST-01-CASHLEG",
    ]
    product, interest, settlement = result.processed_transactions
    assert product.principal_proceeds_local == Decimal("100")
    assert interest.transaction_type == "INTEREST"
    assert interest.gross_transaction_amount == Decimal("5")
    assert interest.external_cash_transaction_id == settlement.transaction_id
    assert settlement.gross_transaction_amount == Decimal("105")
    assert {item.epoch for item in result.processed_transactions} == {4}
    assert [
        call.args[0].transaction_id
        for call in transaction_state.upsert_generated_booked_transaction.await_args_list
    ] == [
        "REDEMPTION-INTEREST-01-CASHLEG",
        "REDEMPTION-INTEREST-01-ACCRUED-INTEREST",
    ]
    assert transaction_state.upsert_booked_transaction.await_count == 1
    assert (
        transaction_state.upsert_booked_transaction.await_args.args[0].transaction_id
        == product.transaction_id
    )


@pytest.mark.asyncio
async def test_redemption_interest_collision_prevents_effect_staging() -> None:
    product_leg = replace(
        _transaction(
            transaction_id="REDEMPTION-COLLISION-01",
            transaction_type="MATURITY_REDEMPTION",
            net_cost_local="100",
            auto_generate_cash_leg=True,
        ),
        quantity=Decimal("1"),
        price=Decimal("100"),
        principal_proceeds_local=Decimal("100"),
        accrued_interest_proceeds_local=Decimal("5"),
    )
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)

    async def reject_interest(transaction: BookedTransaction, **_: object) -> None:
        if transaction.transaction_id.endswith("-ACCRUED-INTEREST"):
            raise GeneratedTransactionIdentityCollisionError(transaction.transaction_id)

    transaction_state.upsert_generated_booked_transaction.side_effect = reject_interest
    effect_stager = AsyncMock(spec=CostProcessingEffectStagingPort)

    with pytest.raises(
        GeneratedTransactionIdentityCollisionError,
        match="generated_transaction_identity_collision",
    ):
        await coordinate_cost_processing_effects(
            tenant_id="tenant-a",
            processed_transactions=[product_leg],
            instrument_updates=[],
            source_epoch=4,
            transaction_state=transaction_state,
            reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
            effect_stager=effect_stager,
            correlation_id="corr-redemption-collision-01",
        )

    effect_stager.stage_processed_transactions.assert_not_awaited()
    effect_stager.stage_instrument_updates.assert_not_awaited()


@pytest.mark.asyncio
async def test_effect_coordination_supersedes_removed_redemption_interest_with_zero() -> None:
    product_leg = replace(
        _transaction(
            transaction_id="REDEMPTION-CORRECTED-01",
            transaction_type="MATURITY_REDEMPTION",
            net_cost_local="100",
            auto_generate_cash_leg=True,
        ),
        quantity=Decimal("1"),
        price=Decimal("100"),
        principal_proceeds_local=Decimal("100"),
        accrued_interest_proceeds_local=Decimal(0),
    )
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)
    transaction_state.get_booked_transaction.return_value = replace(
        product_leg,
        transaction_id="REDEMPTION-CORRECTED-01-ACCRUED-INTEREST",
        transaction_type="INTEREST",
    )

    result = await coordinate_cost_processing_effects(
        tenant_id="tenant-a",
        processed_transactions=[product_leg],
        instrument_updates=[],
        source_epoch=5,
        transaction_state=transaction_state,
        reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
        effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
        correlation_id="corr-redemption-corrected-01",
    )

    zero_interest = result.processed_transactions[1]
    assert zero_interest.transaction_id == "REDEMPTION-CORRECTED-01-ACCRUED-INTEREST"
    assert zero_interest.gross_transaction_amount == Decimal(0)
    assert zero_interest.net_interest_amount == Decimal(0)
    assert zero_interest.epoch == 5


@pytest.mark.asyncio
async def test_corrected_zero_net_redemption_clears_prior_interest_cash_link() -> None:
    corrected = replace(
        _transaction(
            transaction_id="REDEMPTION-ZERO-NET-CORRECTED-01",
            transaction_type="MATURITY_REDEMPTION",
            net_cost_local="0",
        ),
        quantity=Decimal("1"),
        price=Decimal("100"),
        principal_proceeds_local=Decimal(0),
        accrued_interest_proceeds_local=Decimal("5"),
        embedded_fee_amount_local=Decimal("5"),
    )
    prior_interest = redemption.build_redemption_accrued_interest_component(
        replace(
            corrected,
            external_cash_transaction_id="REDEMPTION-ZERO-NET-CORRECTED-01-CASHLEG",
        )
    )
    assert prior_interest is not None
    prior_interest = replace(
        prior_interest,
        external_cash_transaction_id="REDEMPTION-ZERO-NET-CORRECTED-01-CASHLEG",
    )
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)
    transaction_state.get_booked_transaction.side_effect = [None, prior_interest]

    result = await coordinate_cost_processing_effects(
        tenant_id="tenant-a",
        processed_transactions=[corrected],
        instrument_updates=[],
        source_epoch=6,
        transaction_state=transaction_state,
        reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
        effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
        correlation_id="corr-redemption-zero-net-corrected-01",
        corrected_transaction_id=corrected.transaction_id,
    )

    rebuilt_interest = result.processed_transactions[1]
    assert rebuilt_interest.transaction_id == prior_interest.transaction_id
    assert rebuilt_interest.gross_transaction_amount == Decimal("5")
    assert rebuilt_interest.external_cash_transaction_id is None
    assert transaction_state.upsert_generated_booked_transaction.await_args.kwargs == {
        "fields_to_clear": frozenset({"external_cash_transaction_id", "linked_component_ids"})
    }


@pytest.mark.asyncio
async def test_correction_neutralizes_interest_child_after_leaving_redemption() -> None:
    corrected = _transaction(
        transaction_id="REDEMPTION-FAMILY-CORRECTED-01",
        transaction_type="SELL",
        epoch=6,
    )
    original = replace(
        corrected,
        transaction_type="MATURITY_REDEMPTION",
        principal_proceeds_local=Decimal("100"),
        accrued_interest_proceeds_local=Decimal("5"),
        external_cash_transaction_id="REDEMPTION-FAMILY-CORRECTED-01-CASHLEG",
    )
    prior_interest = redemption.build_redemption_accrued_interest_component(original)
    assert prior_interest is not None
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)
    transaction_state.get_booked_transaction.side_effect = [None, prior_interest]

    result = await coordinate_cost_processing_effects(
        tenant_id="tenant-a",
        processed_transactions=[corrected],
        instrument_updates=[],
        source_epoch=6,
        transaction_state=transaction_state,
        reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
        effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
        correlation_id="corr-redemption-family-corrected-01",
        corrected_transaction_id=corrected.transaction_id,
    )

    assert [item.transaction_id for item in result.processed_transactions] == [
        corrected.transaction_id,
        prior_interest.transaction_id,
    ]
    neutralized = result.processed_transactions[1]
    assert neutralized.gross_transaction_amount == Decimal(0)
    assert neutralized.net_interest_amount == Decimal(0)
    assert neutralized.external_cash_transaction_id is None
    assert neutralized.epoch == 6
    assert neutralized.calculation_lineage is not None
    assert transaction_state.upsert_generated_booked_transaction.await_args.kwargs == {
        "fields_to_clear": frozenset({"external_cash_transaction_id", "linked_component_ids"})
    }


@pytest.mark.asyncio
async def test_effect_coordination_reconciles_corporate_action_group_once() -> None:
    source = _transaction(
        transaction_id="CA-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    target = _transaction(
        transaction_id="CA-IN-01",
        transaction_type="DEMERGER_IN",
        net_cost_local="100",
    )
    source = replace(
        source,
        linked_transaction_group_id="LTG-CA-DEM-01",
        parent_event_reference="CA-PARENT-DEM-01",
    )
    target = replace(
        target,
        linked_transaction_group_id="LTG-CA-DEM-01",
        parent_event_reference="CA-PARENT-DEM-01",
    )
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    reconciliation_repository.load_group.return_value = (source, target)
    observer = MagicMock()

    result = await coordinate_cost_processing_effects(
        tenant_id="tenant-a",
        processed_transactions=[source, target],
        instrument_updates=[],
        source_epoch=None,
        transaction_state=AsyncMock(spec=CostBasisTransactionStatePort),
        reconciliation_repository=reconciliation_repository,
        effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
        correlation_id="corr-ca-01",
        reconciliation_observer=observer,
    )

    assert result.processed_transactions == (source, target)
    reconciliation_repository.load_group.assert_awaited_once()
    reconciliation_repository.save_evidence.assert_awaited_once()
    observer.observe.assert_called_once()


@pytest.mark.asyncio
async def test_effect_coordination_stages_instrument_updates_and_count() -> None:
    instrument = MagicMock(spec=FxContractInstrument)
    effect_stager = AsyncMock(spec=CostProcessingEffectStagingPort)

    result = await coordinate_cost_processing_effects(
        tenant_id="tenant-a",
        processed_transactions=[],
        instrument_updates=[instrument],
        source_epoch=None,
        transaction_state=AsyncMock(spec=CostBasisTransactionStatePort),
        reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
        effect_stager=effect_stager,
        correlation_id="corr-instrument-01",
    )

    assert result.instrument_update_count == 1
    effect_stager.stage_instrument_updates.assert_awaited_once_with(
        (instrument,),
        correlation_id="corr-instrument-01",
    )
