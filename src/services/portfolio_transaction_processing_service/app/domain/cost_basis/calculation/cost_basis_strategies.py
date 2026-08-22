"""Implement FIFO and average-cost lot allocation strategies."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, timezone
from decimal import Decimal
from typing import Protocol, cast

from portfolio_common.domain.decimal_amount import required_decimal
from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)

from ..average_cost_allocation_checkpoint import AverageCostAllocationCheckpoint
from ..models.cost_basis_transaction import CostBasisTransaction
from .average_cost_source_allocation import (
    AverageCostPool,
    AverageCostSourceAllocation,
)
from .basis_transfer_allocation import (
    LotBasisTransferResult,
    SourceLotBasisTransferAllocation,
)
from .disposal_allocation import LotDisposalResult, SourceLotDisposalAllocation
from .lot_restatement import LotRestatement
from .lot_state import CostLot, OpenLotState
from .residual_allocation import allocate_nonnegative_storage_share

logger = logging.getLogger(__name__)


def _is_buy_transaction(transaction: CostBasisTransaction) -> bool:
    return str(transaction.transaction_type or "").strip().upper() == "BUY"


def _require_buy_lot_cost_basis(transaction: CostBasisTransaction) -> None:
    if transaction.net_cost is not None and transaction.net_cost_local is not None:
        return
    raise ValueError(
        "Buy transaction "
        f"{transaction.transaction_id} must have net_cost and "
        "net_cost_local calculated before adding as a lot."
    )


def _normalized_buy_lot_amounts(
    transaction: CostBasisTransaction,
) -> tuple[Decimal, Decimal, Decimal]:
    return (
        required_decimal(transaction.quantity, field_name="quantity"),
        required_decimal(transaction.net_cost, field_name="net_cost"),
        required_decimal(transaction.net_cost_local, field_name="net_cost_local"),
    )


def _is_zero_quantity_zero_cost_lot(
    quantity: Decimal, net_cost: Decimal, net_cost_local: Decimal
) -> bool:
    return quantity == Decimal(0) and net_cost == Decimal(0) and net_cost_local == Decimal(0)


def _should_skip_empty_buy_lot(
    transaction: CostBasisTransaction, quantity: Decimal, net_cost: Decimal, net_cost_local: Decimal
) -> bool:
    if quantity > Decimal(0):
        return False
    if _is_zero_quantity_zero_cost_lot(quantity, net_cost, net_cost_local):
        return True
    raise ValueError(
        f"Buy transaction {transaction.transaction_id} must have positive lot quantity."
    )


def _validate_non_negative_buy_lot_cost_basis(
    transaction: CostBasisTransaction, net_cost: Decimal, net_cost_local: Decimal
) -> None:
    if net_cost >= Decimal(0) and net_cost_local >= Decimal(0):
        return
    raise ValueError(
        f"Buy transaction {transaction.transaction_id} must have non-negative lot cost basis."
    )


def _validated_buy_lot_inputs(
    transaction: CostBasisTransaction,
) -> tuple[Decimal, Decimal, Decimal] | None:
    _require_buy_lot_cost_basis(transaction)
    quantity, net_cost, net_cost_local = _normalized_buy_lot_amounts(transaction)
    if _should_skip_empty_buy_lot(transaction, quantity, net_cost, net_cost_local):
        return None
    _validate_non_negative_buy_lot_cost_basis(transaction, net_cost, net_cost_local)
    return quantity, net_cost, net_cost_local


def _non_positive_sell_quantity_error(sell_quantity: Decimal) -> str | None:
    if sell_quantity >= Decimal(0):
        return None
    return f"Sell quantity ({sell_quantity}) must not be negative."


def _utc_transaction_date(transaction: CostBasisTransaction) -> date:
    """Derive the governed acquisition date from the canonical UTC instant."""

    timestamp = transaction.transaction_date
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return cast(date, timestamp.astimezone(timezone.utc).date())


@dataclass(frozen=True, slots=True)
class _UnreconciledSourceDisposalAllocation:
    source_lot_id: str
    source_transaction_id: str
    source_acquisition_date: date
    consumed_quantity: Decimal
    consumed_cost_local: Decimal
    consumed_cost_base: Decimal


def _apportion_nonnegative_disposal_values(
    candidates: list[Decimal],
    *,
    aggregate: Decimal,
    field_name: str,
) -> list[Decimal]:
    """Clamp source rounding noise while preserving the exact aggregate."""

    if not candidates:
        raise ValueError(f"{field_name} disposal requires at least one source allocation")
    allocated = Decimal(0)
    apportioned: list[Decimal] = []
    for candidate in candidates[:-1]:
        share = allocate_nonnegative_storage_share(
            max(candidate, Decimal(0)),
            aggregate=aggregate,
            allocated=allocated,
            field_name=field_name,
        )
        apportioned.append(share)
        allocated = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
            allocated,
            share,
            field_name=f"allocated_{field_name}",
        )
    apportioned.append(
        COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            aggregate,
            allocated,
            field_name=field_name,
        )
    )
    return apportioned


def _reconcile_disposal_allocation_residuals(
    allocations: list[_UnreconciledSourceDisposalAllocation],
    *,
    cost_base: Decimal,
    cost_local: Decimal,
    quantity: Decimal,
) -> list[SourceLotDisposalAllocation]:
    """Reconcile raw source deltas before immutable allocation validation."""

    quantity_sources = [
        allocation for allocation in allocations if allocation.consumed_quantity > 0
    ]
    quantities = _apportion_nonnegative_disposal_values(
        [allocation.consumed_quantity for allocation in quantity_sources],
        aggregate=quantity,
        field_name="consumed_quantity",
    )
    quantity_allocations = [
        (allocation, apportioned_quantity)
        for allocation, apportioned_quantity in zip(quantity_sources, quantities, strict=True)
        if apportioned_quantity > 0
    ]
    local_costs = _apportion_nonnegative_disposal_values(
        [allocation.consumed_cost_local for allocation, _ in quantity_allocations],
        aggregate=cost_local,
        field_name="disposed_cost_local",
    )
    base_costs = _apportion_nonnegative_disposal_values(
        [allocation.consumed_cost_base for allocation, _ in quantity_allocations],
        aggregate=cost_base,
        field_name="disposed_cost_base",
    )
    return [
        SourceLotDisposalAllocation(
            source_lot_id=allocation.source_lot_id,
            source_transaction_id=allocation.source_transaction_id,
            source_acquisition_date=allocation.source_acquisition_date,
            allocation_ordinal=index,
            consumed_quantity=apportioned_quantity,
            consumed_cost_local=local_costs[index - 1],
            consumed_cost_base=base_costs[index - 1],
        )
        for index, (allocation, apportioned_quantity) in enumerate(quantity_allocations, start=1)
    ]


def _consume_next_fifo_lot(
    lots_for_instrument: deque[CostLot],
    required_quantity: Decimal,
    *,
    allocation_ordinal: int,
) -> tuple[SourceLotDisposalAllocation, Decimal]:
    current_lot = lots_for_instrument[0]
    state_before = current_lot.open_state()
    matched_quantity = min(required_quantity, current_lot.remaining_quantity)
    current_lot.remaining_quantity = COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
        current_lot.remaining_quantity,
        matched_quantity,
        field_name="open_quantity",
    )
    if current_lot.remaining_quantity == Decimal(0):
        state_after = OpenLotState(
            original_quantity=current_lot.original_quantity,
            quantity=Decimal(0),
            cost_local=Decimal(0),
            cost_base=Decimal(0),
        )
        lots_for_instrument.popleft()
    else:
        state_after = current_lot.open_state()

    allocation = SourceLotDisposalAllocation(
        source_lot_id=current_lot.lot_id,
        source_transaction_id=current_lot.transaction_id,
        source_acquisition_date=current_lot.acquisition_date,
        allocation_ordinal=allocation_ordinal,
        consumed_cost_base=COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            state_before.cost_base,
            state_after.cost_base,
            field_name="disposed_cost_base",
        ),
        consumed_cost_local=COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            state_before.cost_local,
            state_after.cost_local,
            field_name="disposed_cost_local",
        ),
        consumed_quantity=matched_quantity,
    )
    return (
        allocation,
        COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            required_quantity,
            matched_quantity,
            field_name="remaining_disposal_quantity",
        ),
    )


class CostBasisStrategy(Protocol):
    def add_buy_lot(self, transaction: CostBasisTransaction) -> None: ...
    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> tuple[Decimal, Decimal, Decimal, str | None]: ...
    def consume_sell_quantity_with_allocations(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> LotDisposalResult: ...
    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal: ...
    def restate_lot_quantities(
        self,
        portfolio_id: str,
        instrument_id: str,
        signed_quantity_delta: Decimal,
    ) -> LotRestatement: ...
    def transfer_basis_out(
        self,
        portfolio_id: str,
        instrument_id: str,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> str | None: ...
    def transfer_basis_out_with_allocations(
        self,
        portfolio_id: str,
        instrument_id: str,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> LotBasisTransferResult: ...
    def set_initial_lots(self, transactions: list[CostBasisTransaction]) -> None: ...
    def restore_open_lots(self, transactions: list[CostBasisTransaction]) -> None: ...
    def get_open_lot_states(self) -> dict[str, OpenLotState]: ...


class FIFOBasisStrategy:
    """
    Implements the First-In, First-Out (FIFO) cost basis method.
    """

    def __init__(self) -> None:
        self._open_lots: dict[tuple[str, str], deque[CostLot]] = defaultdict(deque)
        self._lots_by_transaction_id: dict[str, CostLot] = {}
        self._available_quantities: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal(0))
        logger.debug("FIFOBasisStrategy initialized.")

    def add_buy_lot(self, transaction: CostBasisTransaction) -> None:
        validated_inputs = _validated_buy_lot_inputs(transaction)
        if validated_inputs is None:
            return
        quantity, net_cost, net_cost_local = validated_inputs

        with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
            cost_per_share_local = net_cost_local / quantity
            cost_per_share_base = net_cost / quantity

        new_lot = CostLot(
            transaction_id=transaction.transaction_id,
            lot_id=f"LOT-{transaction.transaction_id}",
            acquisition_date=_utc_transaction_date(transaction),
            quantity=quantity,
            cost_per_share_local=cost_per_share_local,
            cost_per_share_base=cost_per_share_base,
            original_quantity=getattr(transaction, "source_lot_original_quantity", quantity),
        )
        key = (transaction.portfolio_id, transaction.instrument_id)
        self._open_lots[key].append(new_lot)
        self._lots_by_transaction_id[transaction.transaction_id] = new_lot
        self._available_quantities[key] = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
            self._available_quantities[key],
            quantity,
            field_name="available_quantity",
        )

    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> tuple[Decimal, Decimal, Decimal, str | None]:
        return self.consume_sell_quantity_with_allocations(
            portfolio_id,
            instrument_id,
            sell_quantity,
        ).legacy_tuple()

    def consume_sell_quantity_with_allocations(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> LotDisposalResult:
        key = (portfolio_id, instrument_id)
        required_quantity = sell_quantity
        total_matched_cost_base = Decimal(0)
        total_matched_cost_local = Decimal(0)
        consumed_quantity = Decimal(0)
        available_qty = self.get_available_quantity(portfolio_id=key[0], instrument_id=key[1])
        invalid_quantity_error = _non_positive_sell_quantity_error(required_quantity)
        if invalid_quantity_error is not None:
            return LotDisposalResult.failed(invalid_quantity_error)

        if required_quantity > available_qty:
            return LotDisposalResult.failed(
                f"Sell quantity ({required_quantity}) exceeds available holdings ({available_qty})."
            )
        if required_quantity == Decimal(0):
            return LotDisposalResult.empty()

        lots_for_instrument = self._open_lots[key]
        allocations: list[SourceLotDisposalAllocation] = []
        while required_quantity > 0 and lots_for_instrument:
            allocation, required_quantity = _consume_next_fifo_lot(
                lots_for_instrument,
                required_quantity,
                allocation_ordinal=len(allocations) + 1,
            )
            allocations.append(allocation)
            total_matched_cost_base = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
                total_matched_cost_base,
                allocation.consumed_cost_base,
                field_name="disposed_cost_base",
            )
            total_matched_cost_local = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
                total_matched_cost_local,
                allocation.consumed_cost_local,
                field_name="disposed_cost_local",
            )
            consumed_quantity = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
                consumed_quantity,
                allocation.consumed_quantity,
                field_name="consumed_quantity",
            )
        self._available_quantities[key] = COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            available_qty,
            consumed_quantity,
            field_name="available_quantity",
        )
        return LotDisposalResult(
            cost_base=total_matched_cost_base,
            cost_local=total_matched_cost_local,
            consumed_quantity=consumed_quantity,
            allocations=tuple(allocations),
        )

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        key = (portfolio_id, instrument_id)
        return self._available_quantities[key]

    def restate_lot_quantities(
        self,
        portfolio_id: str,
        instrument_id: str,
        signed_quantity_delta: Decimal,
    ) -> LotRestatement:
        """Restate every open FIFO lot atomically while conserving total basis."""

        key = (portfolio_id, instrument_id)
        quantity_before = self.get_available_quantity(portfolio_id, instrument_id)
        restatement = LotRestatement.from_signed_delta(
            quantity_before=quantity_before,
            signed_quantity_delta=signed_quantity_delta,
        )
        lots = tuple(self._open_lots[key])
        proposed = tuple(
            (
                lot,
                restatement.apply(
                    lot.original_quantity,
                    field_name="original_quantity",
                ),
                restatement.apply(
                    lot.remaining_quantity,
                    field_name="open_quantity",
                ),
                lot.open_state(),
            )
            for lot in lots
        )
        for lot, original_quantity, open_quantity, state_before in proposed:
            lot.original_quantity = original_quantity
            lot.remaining_quantity = open_quantity
            with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
                lot.cost_per_share_local = state_before.cost_local / open_quantity
                lot.cost_per_share_base = state_before.cost_base / open_quantity
        self._available_quantities[key] = restatement.quantity_after
        return restatement

    def transfer_basis_out(
        self,
        portfolio_id: str,
        instrument_id: str,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> str | None:
        return self.transfer_basis_out_with_allocations(
            portfolio_id,
            instrument_id,
            cost_base,
            cost_local,
        ).error_reason

    def transfer_basis_out_with_allocations(
        self,
        portfolio_id: str,
        instrument_id: str,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> LotBasisTransferResult:
        lots = self._open_lots[(portfolio_id, instrument_id)]
        error = _basis_transfer_error(lots, cost_base=cost_base, cost_local=cost_local)
        if error is not None:
            return LotBasisTransferResult.failed(error)
        open_lots = tuple(lot for lot in lots if lot.remaining_quantity > Decimal(0))
        states_before = tuple(lot.open_state() for lot in open_lots)
        _allocate_fifo_basis_transfer(lots, cost_base=cost_base, cost_local=cost_local)
        return _basis_transfer_result(
            source_lots=tuple(
                (
                    lot.lot_id,
                    lot.transaction_id,
                    lot.acquisition_date,
                    before,
                    lot.open_state(),
                )
                for lot, before in zip(open_lots, states_before, strict=True)
            ),
            transferred_cost_local=cost_local,
            transferred_cost_base=cost_base,
        )

    def set_initial_lots(self, transactions: list[CostBasisTransaction]) -> None:
        for txn in transactions:
            if _is_buy_transaction(txn):
                self.add_buy_lot(txn)

    def restore_open_lots(self, transactions: list[CostBasisTransaction]) -> None:
        for transaction in transactions:
            self.add_buy_lot(transaction)

    def get_open_lot_states(self) -> dict[str, OpenLotState]:
        return {
            transaction_id: lot.open_state()
            for transaction_id, lot in self._lots_by_transaction_id.items()
        }


class AverageCostBasisStrategy(CostBasisStrategy):
    """
    Implements the Average Cost (AVCO) method for tracking cost basis,
    with full support for dual-currency calculations.
    """

    def __init__(self) -> None:
        self._pools: dict[tuple[str, str], AverageCostPool] = defaultdict(AverageCostPool)
        self._source_allocation = AverageCostSourceAllocation()
        logger.debug("AverageCostBasisStrategy initialized.")

    def add_buy_lot(self, transaction: CostBasisTransaction) -> None:
        validated_inputs = _validated_buy_lot_inputs(transaction)
        if validated_inputs is None:
            return
        quantity, net_cost, net_cost_local = validated_inputs

        key = (transaction.portfolio_id, transaction.instrument_id)
        self._pools[key].add(
            quantity=quantity,
            cost_local=net_cost_local,
            cost_base=net_cost,
        )
        self._source_allocation.add_source(
            book_key=key,
            source_transaction_id=transaction.transaction_id,
            source_lot_id=f"LOT-{transaction.transaction_id}",
            source_acquisition_date=_utc_transaction_date(transaction),
            quantity=quantity,
            original_quantity=getattr(transaction, "source_lot_original_quantity", quantity),
            cost_local=net_cost_local,
            cost_base=net_cost,
            pool_quantity_after=self._pools[key].quantity,
        )

    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> tuple[Decimal, Decimal, Decimal, str | None]:
        return self.consume_sell_quantity_with_allocations(
            portfolio_id,
            instrument_id,
            sell_quantity,
        ).legacy_tuple()

    def consume_sell_quantity_with_allocations(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> LotDisposalResult:
        key = (portfolio_id, instrument_id)
        pool = self._pools[key]
        total_qty = pool.quantity
        required_quantity = sell_quantity
        invalid_quantity_error = _non_positive_sell_quantity_error(required_quantity)
        if invalid_quantity_error is not None:
            return LotDisposalResult.failed(invalid_quantity_error)

        if required_quantity > total_qty:
            return LotDisposalResult.failed(
                "Sell quantity "
                f"({required_quantity}) exceeds available average cost "
                f"holdings ({total_qty})."
            )
        if total_qty.is_zero():
            return LotDisposalResult.failed("No holdings to sell against (Average Cost method).")
        if required_quantity == Decimal(0):
            return LotDisposalResult.empty()

        source_contributions = self._source_allocation.active_source_contributions(key)
        states_before = self._source_allocation.materialize_book(book_key=key, pool=pool)
        cogs_base, cogs_local = pool.dispose(required_quantity)
        self._source_allocation.apply_disposal(
            book_key=key,
            quantity_before=total_qty,
            quantity_after=pool.quantity,
        )
        states_after = self._source_allocation.materialize_book(book_key=key, pool=pool)
        allocations: list[_UnreconciledSourceDisposalAllocation] = []
        for source_transaction_id, contribution in source_contributions:
            state_before = states_before[source_transaction_id]
            state_after = states_after.get(
                source_transaction_id,
                OpenLotState(
                    original_quantity=contribution.quantity,
                    quantity=Decimal(0),
                    cost_local=Decimal(0),
                    cost_base=Decimal(0),
                ),
            )
            consumed_quantity = COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
                state_before.quantity,
                state_after.quantity,
                field_name="consumed_quantity",
            )
            allocations.append(
                _UnreconciledSourceDisposalAllocation(
                    source_lot_id=contribution.source_lot_id,
                    source_transaction_id=source_transaction_id,
                    source_acquisition_date=contribution.source_acquisition_date,
                    consumed_quantity=consumed_quantity,
                    consumed_cost_local=COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
                        state_before.cost_local,
                        state_after.cost_local,
                        field_name="disposed_cost_local",
                    ),
                    consumed_cost_base=COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
                        state_before.cost_base,
                        state_after.cost_base,
                        field_name="disposed_cost_base",
                    ),
                )
            )
        reconciled_allocations = _reconcile_disposal_allocation_residuals(
            allocations,
            cost_base=cogs_base,
            cost_local=cogs_local,
            quantity=required_quantity,
        )
        return LotDisposalResult(
            cost_base=cogs_base,
            cost_local=cogs_local,
            consumed_quantity=required_quantity,
            allocations=tuple(reconciled_allocations),
        )

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        key = (portfolio_id, instrument_id)
        return self._pools[key].quantity

    def restate_lot_quantities(
        self,
        portfolio_id: str,
        instrument_id: str,
        signed_quantity_delta: Decimal,
    ) -> LotRestatement:
        """Restate the AVCO pool and every source accumulator without moving basis."""

        key = (portfolio_id, instrument_id)
        pool = self._pools[key]
        restatement = LotRestatement.from_signed_delta(
            quantity_before=pool.quantity,
            signed_quantity_delta=signed_quantity_delta,
        )
        self._source_allocation.apply_quantity_restatement(
            book_key=key,
            restatement=restatement,
        )
        pool.quantity = restatement.quantity_after
        pool.segment_start_quantity = restatement.apply(
            pool.segment_start_quantity,
            field_name="segment_start_quantity",
        )
        return restatement

    def transfer_basis_out(
        self,
        portfolio_id: str,
        instrument_id: str,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> str | None:
        return self.transfer_basis_out_with_allocations(
            portfolio_id,
            instrument_id,
            cost_base,
            cost_local,
        ).error_reason

    def transfer_basis_out_with_allocations(
        self,
        portfolio_id: str,
        instrument_id: str,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> LotBasisTransferResult:
        key = (portfolio_id, instrument_id)
        pool = self._pools[key]
        error = _pool_basis_transfer_error(
            pool,
            cost_base=cost_base,
            cost_local=cost_local,
        )
        if error is not None:
            return LotBasisTransferResult.failed(error)
        states_before = self._source_allocation.materialize_book(book_key=key, pool=pool)
        contributions = self._source_allocation.active_source_contributions(key)
        cost_local_before = pool.cost_local
        cost_base_before = pool.cost_base
        pool.transfer_basis_out(cost_local=cost_local, cost_base=cost_base)
        self._source_allocation.apply_basis_transfer(
            book_key=key,
            cost_local_before=cost_local_before,
            cost_local_after=pool.cost_local,
            cost_base_before=cost_base_before,
            cost_base_after=pool.cost_base,
        )
        states_after = self._source_allocation.materialize_book(book_key=key, pool=pool)
        return _basis_transfer_result(
            source_lots=tuple(
                (
                    contribution.source_lot_id,
                    source_transaction_id,
                    contribution.source_acquisition_date,
                    states_before[source_transaction_id],
                    states_after[source_transaction_id],
                )
                for source_transaction_id, contribution in contributions
            ),
            transferred_cost_local=cost_local,
            transferred_cost_base=cost_base,
        )

    def set_initial_lots(self, transactions: list[CostBasisTransaction]) -> None:
        for txn in transactions:
            if _is_buy_transaction(txn):
                self.add_buy_lot(txn)

    def restore_open_lots(self, transactions: list[CostBasisTransaction]) -> None:
        for transaction in transactions:
            self.add_buy_lot(transaction)

    def get_open_lot_states(self) -> dict[str, OpenLotState]:
        return self._source_allocation.materialize(self._pools)

    def export_allocation_checkpoint(
        self,
        *,
        portfolio_id: str,
        instrument_id: str,
        security_id: str,
    ) -> AverageCostAllocationCheckpoint:
        """Export exact continuation state for one AVCO book."""

        key = (portfolio_id, instrument_id)
        pool = self._pools.get(key)
        if pool is None:
            raise ValueError("Average cost allocation checkpoint book was not found")
        return self._source_allocation.export_checkpoint(
            book_key=key,
            security_id=security_id,
            pool=pool,
        )

    @classmethod
    def from_allocation_checkpoint(
        cls,
        checkpoint: AverageCostAllocationCheckpoint,
    ) -> AverageCostBasisStrategy:
        """Create an AVCO strategy from validated persisted continuation state."""

        strategy = cls()
        key = (checkpoint.pool.portfolio_id, checkpoint.pool.instrument_id)
        strategy._pools[key] = strategy._source_allocation.restore_checkpoint(checkpoint)
        return strategy


def _basis_transfer_error(
    lots: deque[CostLot],
    *,
    cost_base: Decimal,
    cost_local: Decimal,
) -> str | None:
    total_base = sum((lot.open_state().cost_base for lot in lots), Decimal(0))
    total_local = sum((lot.open_state().cost_local for lot in lots), Decimal(0))
    return _basis_transfer_amount_error(
        cost_base=cost_base,
        cost_local=cost_local,
        available_base=total_base,
        available_local=total_local,
    )


def _pool_basis_transfer_error(
    pool: AverageCostPool,
    *,
    cost_base: Decimal,
    cost_local: Decimal,
) -> str | None:
    return _basis_transfer_amount_error(
        cost_base=cost_base,
        cost_local=cost_local,
        available_base=pool.cost_base,
        available_local=pool.cost_local,
    )


def _basis_transfer_amount_error(
    *,
    cost_base: Decimal,
    cost_local: Decimal,
    available_base: Decimal,
    available_local: Decimal,
) -> str | None:
    if cost_base < Decimal(0) or cost_local < Decimal(0):
        return "Basis transfer amounts must not be negative."
    if cost_base > available_base or cost_local > available_local:
        return (
            "Basis transfer exceeds available cost basis "
            f"(requested_base={cost_base}, available_base={available_base}, "
            f"requested_local={cost_local}, available_local={available_local})."
        )
    if available_base <= Decimal(0) or available_local <= Decimal(0):
        return "No positive cost basis is available to transfer."
    return None


def _basis_transfer_result(
    *,
    source_lots: tuple[tuple[str, str, date, OpenLotState, OpenLotState], ...],
    transferred_cost_local: Decimal,
    transferred_cost_base: Decimal,
) -> LotBasisTransferResult:
    allocations: list[SourceLotBasisTransferAllocation] = []
    for source_lot_id, source_transaction_id, acquisition_date, before, after in source_lots:
        local_delta = COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            before.cost_local,
            after.cost_local,
            field_name="transferred_cost_local",
        )
        base_delta = COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            before.cost_base,
            after.cost_base,
            field_name="transferred_cost_base",
        )
        if local_delta.is_zero() and base_delta.is_zero():
            continue
        allocations.append(
            SourceLotBasisTransferAllocation(
                allocation_ordinal=len(allocations) + 1,
                source_lot_id=source_lot_id,
                source_transaction_id=source_transaction_id,
                source_acquisition_date=acquisition_date,
                retained_quantity=after.quantity,
                source_cost_local_before=before.cost_local,
                source_cost_base_before=before.cost_base,
                transferred_cost_local=local_delta,
                transferred_cost_base=base_delta,
                retained_cost_local=after.cost_local,
                retained_cost_base=after.cost_base,
            )
        )
    return LotBasisTransferResult(
        transferred_cost_local=transferred_cost_local,
        transferred_cost_base=transferred_cost_base,
        allocations=tuple(allocations),
    )


def _allocate_fifo_basis_transfer(
    lots: deque[CostLot],
    *,
    cost_base: Decimal,
    cost_local: Decimal,
) -> None:
    open_lots = [lot for lot in lots if lot.remaining_quantity > Decimal(0)]
    total_base = sum((lot.open_state().cost_base for lot in open_lots), Decimal(0))
    total_local = sum((lot.open_state().cost_local for lot in open_lots), Decimal(0))
    remaining_base = total_base - cost_base
    remaining_local = total_local - cost_local
    allocated_base = Decimal(0)
    allocated_local = Decimal(0)
    for lot in open_lots[:-1]:
        state = lot.open_state()
        with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
            raw_next_base = state.cost_base * remaining_base / total_base
            raw_next_local = state.cost_local * remaining_local / total_local
        next_base = allocate_nonnegative_storage_share(
            raw_next_base,
            aggregate=remaining_base,
            allocated=allocated_base,
            field_name="open_cost_base",
        )
        next_local = allocate_nonnegative_storage_share(
            raw_next_local,
            aggregate=remaining_local,
            allocated=allocated_local,
            field_name="open_cost_local",
        )
        _assign_fifo_lot_costs(
            lot,
            cost_base=next_base,
            cost_local=next_local,
        )
        allocated_base = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
            allocated_base,
            next_base,
            field_name="allocated_cost_base",
        )
        allocated_local = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
            allocated_local,
            next_local,
            field_name="allocated_cost_local",
        )
    final_lot = open_lots[-1]
    _assign_fifo_lot_costs(
        final_lot,
        cost_base=COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            remaining_base,
            allocated_base,
            field_name="open_cost_base",
        ),
        cost_local=COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            remaining_local,
            allocated_local,
            field_name="open_cost_local",
        ),
    )


def _assign_fifo_lot_costs(
    lot: CostLot,
    *,
    cost_base: Decimal,
    cost_local: Decimal,
) -> None:
    with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
        lot.cost_per_share_base = cost_base / lot.remaining_quantity
        lot.cost_per_share_local = cost_local / lot.remaining_quantity
