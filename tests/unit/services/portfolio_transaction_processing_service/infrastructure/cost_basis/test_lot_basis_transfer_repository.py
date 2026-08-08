"""Verify basis-transfer receipt versioning, voiding, and corruption handling."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import (
    LotBasisTransferAllocationRecord,
    LotBasisTransferReceiptRecord,
)
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LotBasisTransferReceiptState,
    LotBasisTransferReceiptStatus,
    LotBasisTransferReconciliationScope,
    SourceLotBasisTransferAllocation,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    lot_basis_transfer_repository,
)


def _lineage(algorithm_id: str) -> CalculationLineage:
    return build_calculation_lineage(
        algorithm_id=algorithm_id,
        algorithm_version=1,
        intermediate_precision=38,
        input_payload={"transaction_id": "DEMERGER-OUT-01"},
        output_payload={"cost": Decimal("25")},
    )


def _active_state(*, transferred_local: str = "25") -> LotBasisTransferReceiptState:
    transferred = Decimal(transferred_local)
    return LotBasisTransferReceiptState(
        source_transaction_id="DEMERGER-OUT-01",
        target_transaction_id="DEMERGER-IN-01",
        target_lot_id="LOT-DEMERGER-IN-01",
        portfolio_id="PORT-01",
        source_instrument_id="SOURCE-INSTRUMENT-01",
        source_security_id="SOURCE-SECURITY-01",
        target_instrument_id="TARGET-INSTRUMENT-01",
        transfer_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
        transaction_type="DEMERGER_OUT",
        cost_basis_method=CostBasisMethod.FIFO,
        calculation_policy_id="cost-basis-default",
        calculation_policy_version="1",
        transaction_calculation_lineage=_lineage("transaction-cost"),
        status=LotBasisTransferReceiptStatus.ACTIVE,
        transferred_cost_local=transferred,
        transferred_cost_base=Decimal("30"),
        allocations=(
            SourceLotBasisTransferAllocation(
                allocation_ordinal=1,
                source_lot_id="LOT-BUY-01",
                source_transaction_id="BUY-01",
                source_acquisition_date=date(2026, 1, 1),
                retained_quantity=Decimal("10"),
                source_cost_local_before=Decimal("100"),
                source_cost_base_before=Decimal("120"),
                transferred_cost_local=transferred,
                transferred_cost_base=Decimal("30"),
                retained_cost_local=Decimal("100") - transferred,
                retained_cost_base=Decimal("90"),
            ),
        ),
        basis_transfer_calculation_lineage=_lineage("basis-transfer"),
    )


def _scope(*, transaction_type: str = "DEMERGER_OUT") -> LotBasisTransferReconciliationScope:
    state = _active_state()
    return LotBasisTransferReconciliationScope(
        source_transaction_id=state.source_transaction_id,
        portfolio_id=state.portfolio_id,
        source_instrument_id=state.source_instrument_id,
        source_security_id=state.source_security_id,
        transfer_timestamp=state.transfer_timestamp,
        transaction_type=transaction_type,
        cost_basis_method=state.cost_basis_method,
        calculation_policy_id=state.calculation_policy_id,
        calculation_policy_version=state.calculation_policy_version,
        transaction_calculation_lineage=_lineage("current-transaction-cost"),
    )


def _persisted_version(
    state: LotBasisTransferReceiptState,
    *,
    version: int = 1,
    previous: LotBasisTransferReceiptRecord | None = None,
) -> tuple[LotBasisTransferReceiptRecord, tuple[LotBasisTransferAllocationRecord, ...]]:
    previous_hash = str(previous.receipt_content_hash) if previous is not None else None
    receipt_hash = lot_basis_transfer_repository._receipt_content_hash(
        state=state,
        receipt_version=version,
        previous_receipt_content_hash=previous_hash,
    )
    record = LotBasisTransferReceiptRecord(
        **lot_basis_transfer_repository._header_values(
            state=state,
            receipt_version=version,
            previous_receipt_content_hash=previous_hash,
            receipt_content_hash=receipt_hash,
        )
    )
    allocations = tuple(
        LotBasisTransferAllocationRecord(**values)
        for values in lot_basis_transfer_repository._allocation_values(
            state=state,
            receipt_version=version,
        )
    )
    return record, allocations


def _repository_with_latest(
    state: LotBasisTransferReceiptState,
) -> tuple[object, AsyncMock]:
    record, allocations = _persisted_version(state)
    session = AsyncMock()
    repository = lot_basis_transfer_repository.SqlAlchemyCostBasisLotBasisTransferRepository(
        session
    )
    repository._load_receipt_chains = AsyncMock(  # type: ignore[method-assign]
        return_value={state.source_transaction_id: (record,)}
    )
    repository._load_allocations = AsyncMock(  # type: ignore[method-assign]
        return_value={(state.receipt_id, 1): allocations}
    )
    return repository, session


def test_verified_state_reconstructs_complete_active_receipt() -> None:
    state = _active_state()
    record, allocations = _persisted_version(state)

    reconstructed = lot_basis_transfer_repository._verified_state(
        record,
        allocations=allocations,
        previous_record=None,
    )

    assert reconstructed == state


def test_verified_state_fails_closed_for_tampered_allocation_hash() -> None:
    record, allocations = _persisted_version(_active_state())
    allocations[0].allocation_content_hash = "0" * 64

    with pytest.raises(lot_basis_transfer_repository.CorruptLotBasisTransferReceiptError):
        lot_basis_transfer_repository._verified_state(
            record,
            allocations=allocations,
            previous_record=None,
        )


def test_verified_state_fails_closed_for_missing_predecessor() -> None:
    first, _ = _persisted_version(_active_state())
    second, allocations = _persisted_version(
        _active_state(transferred_local="30"),
        version=2,
        previous=first,
    )

    with pytest.raises(lot_basis_transfer_repository.CorruptLotBasisTransferReceiptError):
        lot_basis_transfer_repository._verified_state(
            second,
            allocations=allocations,
            previous_record=None,
        )


@pytest.mark.asyncio
async def test_exact_retry_is_write_neutral() -> None:
    state = _active_state()
    repository, session = _repository_with_latest(state)

    await repository.reconcile_basis_transfer_receipts(  # type: ignore[attr-defined]
        reconciliation_scopes=(_scope(),),
        receipt_states=(state,),
    )

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciliation_verifies_every_transfer_version_before_retry() -> None:
    state = _active_state()
    chain: list[LotBasisTransferReceiptRecord] = []
    allocations_by_version: dict[tuple[str, int], tuple[LotBasisTransferAllocationRecord, ...]] = {}
    previous: LotBasisTransferReceiptRecord | None = None
    for version in range(1, 65):
        record, allocations = _persisted_version(state, version=version, previous=previous)
        chain.append(record)
        allocations_by_version[(state.receipt_id, version)] = allocations
        previous = record
    allocations_by_version[(state.receipt_id, 32)][0].allocation_content_hash = "0" * 64

    session = AsyncMock()
    repository = lot_basis_transfer_repository.SqlAlchemyCostBasisLotBasisTransferRepository(
        session
    )
    repository._load_receipt_chains = AsyncMock(  # type: ignore[method-assign]
        return_value={state.source_transaction_id: tuple(chain)}
    )
    repository._load_allocations = AsyncMock(  # type: ignore[method-assign]
        return_value=allocations_by_version
    )

    with pytest.raises(
        lot_basis_transfer_repository.CorruptLotBasisTransferReceiptError,
        match="receipt chain is corrupt",
    ):
        await repository.reconcile_basis_transfer_receipts(
            reconciliation_scopes=(_scope(),),
            receipt_states=(state,),
        )

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_changed_receipt_appends_header_and_children() -> None:
    repository, session = _repository_with_latest(_active_state())

    await repository.reconcile_basis_transfer_receipts(  # type: ignore[attr-defined]
        reconciliation_scopes=(_scope(),),
        receipt_states=(_active_state(transferred_local="30"),),
    )

    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_removed_transfer_appends_void_with_current_transaction_lineage() -> None:
    state = _active_state()
    repository, session = _repository_with_latest(state)
    scope = _scope(transaction_type="ADJUSTMENT")

    await repository.reconcile_basis_transfer_receipts(  # type: ignore[attr-defined]
        reconciliation_scopes=(scope,),
        receipt_states=(),
    )

    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    parameters = statement.compile().params
    assert "ADJUSTMENT" in parameters.values()
    assert "RECALCULATED_WITHOUT_BASIS_TRANSFER" in parameters.values()


@pytest.mark.asyncio
async def test_initial_absent_transfer_does_not_create_empty_history() -> None:
    session = AsyncMock()
    repository = lot_basis_transfer_repository.SqlAlchemyCostBasisLotBasisTransferRepository(
        session
    )
    repository._load_receipt_chains = AsyncMock(return_value={})  # type: ignore[method-assign]
    repository._load_allocations = AsyncMock(return_value={})  # type: ignore[method-assign]

    await repository.reconcile_basis_transfer_receipts(
        reconciliation_scopes=(_scope(),),
        receipt_states=(),
    )

    session.execute.assert_not_awaited()


def test_void_builder_rejects_changed_source_scope() -> None:
    changed_scope = replace(_scope(), source_security_id="OTHER-SECURITY")

    with pytest.raises(ValueError, match="changed receipt identity"):
        LotBasisTransferReceiptState.voided_from(
            previous=_active_state(),
            scope=changed_scope,
            reason="REMOVED",
        )
