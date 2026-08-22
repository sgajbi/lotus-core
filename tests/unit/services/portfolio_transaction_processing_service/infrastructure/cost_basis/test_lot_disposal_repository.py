"""Verify immutable lot-disposal receipt reconciliation and corruption handling."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import (
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
)
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.domain.cost_basis_receipt_integrity import (
    canonical_cost_basis_output_payload,
)

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AmortizedCostAllocationEvidence,
    LotDisposalDestination,
    LotDisposalDestinationType,
    LotDisposalReceiptState,
    LotDisposalReceiptStatus,
    SourceLotDisposalAllocation,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    lot_disposal_repository,
)


def _lineage(algorithm_id: str) -> CalculationLineage:
    return build_calculation_lineage(
        algorithm_id=algorithm_id,
        algorithm_version=1,
        intermediate_precision=38,
        input_payload={"transaction_id": "SELL-REPOSITORY-01"},
        output_payload={"cost": Decimal("10")},
    )


def _active_state(*, cost_local: str = "10") -> LotDisposalReceiptState:
    return LotDisposalReceiptState(
        disposal_transaction_id="SELL-REPOSITORY-01",
        portfolio_id="PORT-REPOSITORY-01",
        instrument_id="INSTRUMENT-REPOSITORY-01",
        security_id="SECURITY-REPOSITORY-01",
        disposal_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
        transaction_type="SELL",
        cost_basis_method=CostBasisMethod.FIFO,
        calculation_policy_id="cost-basis-default",
        calculation_policy_version="1",
        transaction_calculation_lineage=_lineage("transaction-cost"),
        status=LotDisposalReceiptStatus.ACTIVE,
        consumed_quantity=Decimal("1"),
        consumed_cost_local=Decimal(cost_local),
        consumed_cost_base=Decimal("10"),
        allocations=(
            SourceLotDisposalAllocation(
                source_lot_id="LOT-REPOSITORY-01",
                source_transaction_id="BUY-REPOSITORY-01",
                source_acquisition_date=date(2026, 1, 1),
                allocation_ordinal=1,
                consumed_quantity=Decimal("1"),
                consumed_cost_local=Decimal(cost_local),
                consumed_cost_base=Decimal("10"),
            ),
        ),
        disposal_calculation_lineage=_lineage("lot-disposal"),
    )


def _internal_transfer_state() -> LotDisposalReceiptState:
    return replace(
        _active_state(),
        transaction_type="TRANSFER_OUT",
        destination=LotDisposalDestination(
            destination_type=LotDisposalDestinationType.INTERNAL_LOT,
            target_transaction_id="TRANSFER-IN-REPOSITORY-01",
            target_lot_id="LOT-TRANSFER-IN-REPOSITORY-01",
            target_instrument_id="INSTRUMENT-TARGET-01",
        ),
    )


def _active_state_with_amortized_cost() -> LotDisposalReceiptState:
    state = _active_state(cost_local="11")
    output_payload = {
        "consumed_cost_base": Decimal("11"),
        "consumed_cost_local": Decimal("11"),
        "consumed_quantity": Decimal("1"),
        "current_cost_base": Decimal("110"),
        "current_cost_local": Decimal("110"),
        "open_quantity_before": Decimal("10"),
        "recognized_through_date": date(2026, 6, 30),
        "residual_cost_base": Decimal("99"),
        "residual_cost_local": Decimal("99"),
        "residual_quantity": Decimal("9"),
        "retained_rounding_residual_base": Decimal("0"),
        "retained_rounding_residual_local": Decimal("0"),
        "scheduled_cost_local": Decimal("110"),
    }
    evidence = AmortizedCostAllocationEvidence(
        profile_id="PROFILE-REPOSITORY-01",
        profile_version=2,
        profile_content_hash="a" * 64,
        currency="USD",
        disposal_date=date(2026, 7, 1),
        recognized_through_date=date(2026, 6, 30),
        original_quantity=Decimal("10"),
        open_quantity_before=Decimal("10"),
        consumed_quantity=Decimal("1"),
        residual_quantity=Decimal("9"),
        scheduled_cost_local=Decimal("110"),
        current_cost_local=Decimal("110"),
        current_cost_base=Decimal("110"),
        consumed_cost_local=Decimal("11"),
        residual_cost_local=Decimal("99"),
        book_cost_fx_rate_to_base=Decimal("1"),
        consumed_cost_base=Decimal("11"),
        residual_cost_base=Decimal("99"),
        retained_rounding_residual_local=Decimal("0"),
        retained_rounding_residual_base=Decimal("0"),
        calculation_lineage=build_calculation_lineage(
            algorithm_id="fixed-income-amortized-cost-disposal",
            algorithm_version=1,
            intermediate_precision=38,
            input_payload={"profile_id": "PROFILE-REPOSITORY-01"},
            output_payload=canonical_cost_basis_output_payload(output_payload),
        ),
    )
    allocation = replace(
        state.allocations[0],
        consumed_cost_local=Decimal("11"),
        consumed_cost_base=Decimal("11"),
        amortized_cost_evidence=evidence,
    )
    return replace(
        state,
        consumed_cost_local=Decimal("11"),
        consumed_cost_base=Decimal("11"),
        allocations=(allocation,),
    )


def _void_state() -> LotDisposalReceiptState:
    active = _active_state()
    return LotDisposalReceiptState(
        disposal_transaction_id=active.disposal_transaction_id,
        portfolio_id=active.portfolio_id,
        instrument_id=active.instrument_id,
        security_id=active.security_id,
        disposal_timestamp=active.disposal_timestamp,
        transaction_type="BUY",
        cost_basis_method=active.cost_basis_method,
        calculation_policy_id=active.calculation_policy_id,
        calculation_policy_version=active.calculation_policy_version,
        transaction_calculation_lineage=_lineage("corrected-transaction-cost"),
        status=LotDisposalReceiptStatus.VOIDED,
        consumed_quantity=Decimal(0),
        consumed_cost_local=Decimal(0),
        consumed_cost_base=Decimal(0),
        allocations=(),
        disposal_calculation_lineage=None,
        void_reason="RECALCULATED_WITHOUT_LOT_DISPOSAL",
    )


def _persisted_version(
    state: LotDisposalReceiptState,
    *,
    version: int = 1,
    previous: LotDisposalReceiptRecord | None = None,
) -> tuple[LotDisposalReceiptRecord, tuple[LotDisposalAllocationRecord, ...]]:
    previous_hash = str(previous.receipt_content_hash) if previous is not None else None
    receipt_hash = lot_disposal_repository._receipt_content_hash(
        state=state,
        receipt_version=version,
        previous_receipt_content_hash=previous_hash,
    )
    record = LotDisposalReceiptRecord(
        **lot_disposal_repository._header_values(
            state=state,
            receipt_version=version,
            previous_receipt_content_hash=previous_hash,
            receipt_content_hash=receipt_hash,
        )
    )
    allocations = tuple(
        LotDisposalAllocationRecord(**values)
        for values in lot_disposal_repository._allocation_values(
            state=state,
            receipt_version=version,
        )
    )
    return record, allocations


def test_verified_state_reconstructs_complete_active_receipt() -> None:
    state = _active_state()
    record, allocations = _persisted_version(state)

    reconstructed = lot_disposal_repository._verified_state(
        record,
        allocations=allocations,
        previous_record=None,
    )

    assert reconstructed == state


def test_verified_state_reconstructs_internal_transfer_destination() -> None:
    state = _internal_transfer_state()
    record, allocations = _persisted_version(state)

    reconstructed = lot_disposal_repository._verified_state(
        record,
        allocations=allocations,
        previous_record=None,
    )

    assert reconstructed == state


@pytest.mark.parametrize(
    ("field_name", "tampered_value"),
    (
        ("destination_type", None),
        ("target_transaction_id", "TRANSFER-IN-TAMPERED"),
        ("target_lot_id", "LOT-TRANSFER-IN-TAMPERED"),
        ("target_instrument_id", "INSTRUMENT-TAMPERED"),
        ("external_destination_reference", "EXTERNAL-ACCOUNT-01"),
    ),
)
def test_verified_state_fails_closed_for_tampered_destination(
    field_name: str,
    tampered_value: str | None,
) -> None:
    state = _internal_transfer_state()
    record, allocations = _persisted_version(state)
    setattr(record, field_name, tampered_value)

    with pytest.raises(
        lot_disposal_repository.CorruptLotDisposalReceiptError,
        match="persisted lot-disposal receipt is corrupt",
    ):
        lot_disposal_repository._verified_state(
            record,
            allocations=allocations,
            previous_record=None,
        )


def test_verified_state_reconstructs_amortized_cost_evidence() -> None:
    state = _active_state_with_amortized_cost()
    record, allocations = _persisted_version(state)

    reconstructed = lot_disposal_repository._verified_state(
        record,
        allocations=allocations,
        previous_record=None,
    )

    assert reconstructed == state
    assert reconstructed.allocations[0].amortized_cost_evidence is not None


def test_verified_state_fails_closed_for_partial_amortized_cost_evidence() -> None:
    state = _active_state_with_amortized_cost()
    record, allocations = _persisted_version(state)
    allocations[0].amortized_cost_currency = None

    with pytest.raises(
        lot_disposal_repository.CorruptLotDisposalReceiptError,
        match="persisted lot-disposal receipt is corrupt",
    ):
        lot_disposal_repository._verified_state(
            record,
            allocations=allocations,
            previous_record=None,
        )


def test_verified_state_fails_closed_for_tampered_allocation_hash() -> None:
    state = _active_state()
    record, allocations = _persisted_version(state)
    allocations[0].allocation_content_hash = "0" * 64

    with pytest.raises(
        lot_disposal_repository.CorruptLotDisposalReceiptError,
        match="persisted lot-disposal receipt is corrupt",
    ):
        lot_disposal_repository._verified_state(
            record,
            allocations=allocations,
            previous_record=None,
        )


def test_verified_state_fails_closed_for_missing_predecessor() -> None:
    first, _ = _persisted_version(_active_state())
    second, allocations = _persisted_version(
        _active_state(cost_local="11"),
        version=2,
        previous=first,
    )

    with pytest.raises(
        lot_disposal_repository.CorruptLotDisposalReceiptError,
        match="persisted lot-disposal receipt is corrupt",
    ):
        lot_disposal_repository._verified_state(
            second,
            allocations=allocations,
            previous_record=None,
        )


@pytest.mark.asyncio
async def test_exact_retry_is_write_neutral() -> None:
    state = _active_state()
    record, allocations = _persisted_version(state)
    session = AsyncMock()
    repository = lot_disposal_repository.SqlAlchemyCostBasisLotDisposalRepository(session)
    repository._load_receipt_chains = AsyncMock(  # type: ignore[method-assign]
        return_value={state.disposal_transaction_id: (record,)}
    )
    repository._load_allocations = AsyncMock(  # type: ignore[method-assign]
        return_value={(state.receipt_id, 1): allocations}
    )

    await repository.reconcile_disposal_receipts(receipt_states=(state,))

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_with_transient_quantity_authority_is_write_neutral() -> None:
    persisted_state = _active_state()
    record, allocations = _persisted_version(persisted_state)
    candidate = replace(
        persisted_state,
        allocations=(
            replace(
                persisted_state.allocations[0],
                source_original_quantity=Decimal("4"),
                source_open_quantity_before=Decimal("3"),
            ),
        ),
    )
    session = AsyncMock()
    repository = lot_disposal_repository.SqlAlchemyCostBasisLotDisposalRepository(session)
    repository._load_receipt_chains = AsyncMock(  # type: ignore[method-assign]
        return_value={persisted_state.disposal_transaction_id: (record,)}
    )
    repository._load_allocations = AsyncMock(  # type: ignore[method-assign]
        return_value={(persisted_state.receipt_id, 1): allocations}
    )

    assert candidate != persisted_state
    assert candidate.semantic_payload() == persisted_state.semantic_payload()

    await repository.reconcile_disposal_receipts(receipt_states=(candidate,))

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciliation_verifies_every_version_before_accepting_retry() -> None:
    state = _active_state()
    chain: list[LotDisposalReceiptRecord] = []
    allocations_by_version: dict[tuple[str, int], tuple[LotDisposalAllocationRecord, ...]] = {}
    previous: LotDisposalReceiptRecord | None = None
    for version in range(1, 65):
        record, allocations = _persisted_version(state, version=version, previous=previous)
        chain.append(record)
        allocations_by_version[(state.receipt_id, version)] = allocations
        previous = record
    allocations_by_version[(state.receipt_id, 32)][0].allocation_content_hash = "0" * 64

    session = AsyncMock()
    repository = lot_disposal_repository.SqlAlchemyCostBasisLotDisposalRepository(session)
    repository._load_receipt_chains = AsyncMock(  # type: ignore[method-assign]
        return_value={state.disposal_transaction_id: tuple(chain)}
    )
    repository._load_allocations = AsyncMock(  # type: ignore[method-assign]
        return_value=allocations_by_version
    )

    with pytest.raises(
        lot_disposal_repository.CorruptLotDisposalReceiptError,
        match="receipt is corrupt",
    ):
        await repository.reconcile_disposal_receipts(receipt_states=(state,))

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_changed_receipt_appends_header_and_children() -> None:
    first_state = _active_state()
    first, allocations = _persisted_version(first_state)
    corrected = _active_state(cost_local="11")
    session = AsyncMock()
    repository = lot_disposal_repository.SqlAlchemyCostBasisLotDisposalRepository(session)
    repository._load_receipt_chains = AsyncMock(  # type: ignore[method-assign]
        return_value={first_state.disposal_transaction_id: (first,)}
    )
    repository._load_allocations = AsyncMock(  # type: ignore[method-assign]
        return_value={(first_state.receipt_id, 1): allocations}
    )

    await repository.reconcile_disposal_receipts(receipt_states=(corrected,))

    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_active_to_voided_appends_header_without_children() -> None:
    active = _active_state()
    first, allocations = _persisted_version(active)
    voided = _void_state()
    session = AsyncMock()
    repository = lot_disposal_repository.SqlAlchemyCostBasisLotDisposalRepository(session)
    repository._load_receipt_chains = AsyncMock(  # type: ignore[method-assign]
        return_value={active.disposal_transaction_id: (first,)}
    )
    repository._load_allocations = AsyncMock(  # type: ignore[method-assign]
        return_value={(active.receipt_id, 1): allocations}
    )

    await repository.reconcile_disposal_receipts(receipt_states=(voided,))

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_initial_void_state_does_not_create_empty_history() -> None:
    voided = _void_state()
    session = AsyncMock()
    repository = lot_disposal_repository.SqlAlchemyCostBasisLotDisposalRepository(session)
    repository._load_receipt_chains = AsyncMock(  # type: ignore[method-assign]
        return_value={}
    )
    repository._load_allocations = AsyncMock(  # type: ignore[method-assign]
        return_value={}
    )

    await repository.reconcile_disposal_receipts(receipt_states=(voided,))

    session.execute.assert_not_awaited()
