"""SQLAlchemy adapter for immutable versioned lot basis-transfer receipts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import cast

from portfolio_common.database_models import (
    LotBasisTransferAllocationRecord,
    LotBasisTransferReceiptRecord,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.domain.cost_basis_receipt_integrity import (
    cost_basis_allocation_content_hash,
    verify_cost_basis_receipt_version_chain,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cost_basis import (
    LotBasisTransferReceiptState,
    LotBasisTransferReceiptStatus,
    LotBasisTransferReconciliationScope,
    SourceLotBasisTransferAllocation,
)
from .receipt_integrity import receipt_version_content_hash, required_calculation_lineage


class CorruptLotBasisTransferReceiptError(ValueError):
    """Raised when persisted basis-transfer evidence fails reconstruction."""


class ConflictingLotBasisTransferReceiptError(ValueError):
    """Raised when an immutable receipt version collides during append."""


class SqlAlchemyCostBasisLotBasisTransferRepository:
    """Append corrections, void removed evidence, and neutralize exact retries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reconcile_basis_transfer_receipts(
        self,
        *,
        reconciliation_scopes: tuple[LotBasisTransferReconciliationScope, ...],
        receipt_states: tuple[LotBasisTransferReceiptState, ...],
    ) -> None:
        """Reconcile one current state for every source in the affected suffix."""

        if not reconciliation_scopes:
            if receipt_states:
                raise ValueError("basis-transfer receipts require reconciliation scopes")
            return
        scopes_by_transaction = _validate_candidate_batch(
            reconciliation_scopes=reconciliation_scopes,
            receipt_states=receipt_states,
        )
        candidates_by_transaction = {state.source_transaction_id: state for state in receipt_states}
        transaction_ids = tuple(scopes_by_transaction)
        chains = await self._load_receipt_chains(transaction_ids)
        persisted_records = tuple(record for chain in chains.values() for record in chain)
        persisted_allocations = await self._load_allocations(persisted_records)
        latest: dict[str, LotBasisTransferReceiptRecord] = {}
        verified_latest: dict[str, LotBasisTransferReceiptState] = {}
        for transaction_id, chain in chains.items():
            try:
                verify_cost_basis_receipt_version_chain(chain)
                verified_states = tuple(
                    _verified_state(
                        record,
                        allocations=persisted_allocations.get(
                            (str(record.receipt_id), int(record.receipt_version)),
                            (),
                        ),
                        previous_record=chain[index - 1] if index else None,
                    )
                    for index, record in enumerate(chain)
                )
            except ValueError as exc:
                raise CorruptLotBasisTransferReceiptError(
                    f"persisted lot basis-transfer receipt is corrupt: {transaction_id}"
                ) from exc
            latest[transaction_id] = chain[-1]
            verified_latest[transaction_id] = verified_states[-1]

        header_values: list[dict[str, object]] = []
        allocation_values: list[dict[str, object]] = []
        for transaction_id, scope in scopes_by_transaction.items():
            prior_record = latest.get(transaction_id)
            prior_state = verified_latest.get(transaction_id)
            state = candidates_by_transaction.get(transaction_id)
            if state is None:
                if (
                    prior_state is None
                    or prior_state.status is LotBasisTransferReceiptStatus.VOIDED
                ):
                    continue
                state = LotBasisTransferReceiptState.voided_from(
                    previous=prior_state,
                    scope=scope,
                    reason="RECALCULATED_WITHOUT_BASIS_TRANSFER",
                )
            if prior_record is None:
                if state.status is LotBasisTransferReceiptStatus.VOIDED:
                    continue
                receipt_version = 1
                previous_hash = None
            else:
                if prior_state is None:
                    raise CorruptLotBasisTransferReceiptError(
                        f"latest receipt state was not verified: {state.receipt_id}"
                    )
                _require_same_receipt_identity(prior_state, state)
                if prior_state.semantic_content_hash == state.semantic_content_hash:
                    if prior_state != state:
                        raise CorruptLotBasisTransferReceiptError(
                            "receipt semantic hash matched different reconstructed content: "
                            f"{state.receipt_id}"
                        )
                    continue
                receipt_version = int(prior_record.receipt_version) + 1
                previous_hash = str(prior_record.receipt_content_hash)

            receipt_hash = _receipt_content_hash(
                state=state,
                receipt_version=receipt_version,
                previous_receipt_content_hash=previous_hash,
            )
            header_values.append(
                _header_values(
                    state=state,
                    receipt_version=receipt_version,
                    previous_receipt_content_hash=previous_hash,
                    receipt_content_hash=receipt_hash,
                )
            )
            allocation_values.extend(
                _allocation_values(state=state, receipt_version=receipt_version)
            )

        if not header_values:
            return
        try:
            await self._session.execute(
                pg_insert(LotBasisTransferReceiptRecord).values(header_values)
            )
            if allocation_values:
                await self._session.execute(
                    pg_insert(LotBasisTransferAllocationRecord).values(allocation_values)
                )
        except IntegrityError as exc:
            raise ConflictingLotBasisTransferReceiptError(
                "lot basis-transfer receipt version collided during append"
            ) from exc

    async def _load_receipt_chains(
        self,
        transaction_ids: tuple[str, ...],
    ) -> dict[str, tuple[LotBasisTransferReceiptRecord, ...]]:
        record = LotBasisTransferReceiptRecord
        rows = (
            await self._session.scalars(
                select(record)
                .where(record.source_transaction_id.in_(transaction_ids))
                .order_by(record.source_transaction_id, record.receipt_version)
            )
        ).all()
        grouped: defaultdict[str, list[LotBasisTransferReceiptRecord]] = defaultdict(list)
        for row in rows:
            grouped[str(row.source_transaction_id)].append(row)
        return {transaction_id: tuple(items) for transaction_id, items in grouped.items()}

    async def _load_allocations(
        self,
        receipts: tuple[LotBasisTransferReceiptRecord, ...],
    ) -> dict[tuple[str, int], tuple[LotBasisTransferAllocationRecord, ...]]:
        receipt_ids = {str(record.receipt_id) for record in receipts}
        if not receipt_ids:
            return {}
        allocation = LotBasisTransferAllocationRecord
        rows = (
            await self._session.scalars(
                select(allocation)
                .where(allocation.receipt_id.in_(receipt_ids))
                .order_by(
                    allocation.receipt_id,
                    allocation.receipt_version,
                    allocation.allocation_ordinal,
                )
            )
        ).all()
        grouped: defaultdict[tuple[str, int], list[LotBasisTransferAllocationRecord]] = defaultdict(
            list
        )
        for row in rows:
            grouped[(str(row.receipt_id), int(row.receipt_version))].append(row)
        return {identity: tuple(items) for identity, items in grouped.items()}


def _validate_candidate_batch(
    *,
    reconciliation_scopes: Sequence[LotBasisTransferReconciliationScope],
    receipt_states: Sequence[LotBasisTransferReceiptState],
) -> dict[str, LotBasisTransferReconciliationScope]:
    if not all(
        isinstance(scope, LotBasisTransferReconciliationScope) for scope in reconciliation_scopes
    ):
        raise TypeError(
            "reconciliation_scopes must contain LotBasisTransferReconciliationScope values"
        )
    if not all(isinstance(state, LotBasisTransferReceiptState) for state in receipt_states):
        raise TypeError("receipt_states must contain LotBasisTransferReceiptState values")
    scopes_by_transaction = {scope.source_transaction_id: scope for scope in reconciliation_scopes}
    if len(scopes_by_transaction) != len(reconciliation_scopes):
        raise ValueError("reconciliation scope contains duplicate transaction identities")
    receipt_ids = [state.receipt_id for state in receipt_states]
    transaction_ids = [state.source_transaction_id for state in receipt_states]
    if len(set(receipt_ids)) != len(receipt_ids):
        raise ValueError("receipt batch contains duplicate receipt identities")
    if len(set(transaction_ids)) != len(transaction_ids):
        raise ValueError("receipt batch contains duplicate transaction identities")
    if not set(transaction_ids).issubset(scopes_by_transaction):
        raise ValueError("receipt batch contains a transaction outside reconciliation scope")
    for state in receipt_states:
        scope = scopes_by_transaction[state.source_transaction_id]
        if (
            state.portfolio_id != scope.portfolio_id
            or state.source_security_id != scope.source_security_id
        ):
            raise ValueError("receipt state differs from its reconciliation scope")
    return scopes_by_transaction


def _verified_state(
    record: LotBasisTransferReceiptRecord,
    *,
    allocations: Sequence[LotBasisTransferAllocationRecord],
    previous_record: LotBasisTransferReceiptRecord | None,
) -> LotBasisTransferReceiptState:
    try:
        version = int(record.receipt_version)
        previous_hash = (
            str(record.previous_receipt_content_hash)
            if record.previous_receipt_content_hash is not None
            else None
        )
        if version == 1:
            if previous_hash is not None or previous_record is not None:
                raise ValueError("first receipt version cannot have a predecessor")
        else:
            if previous_record is None:
                raise ValueError("receipt version chain has a missing predecessor")
            if previous_hash != str(previous_record.receipt_content_hash):
                raise ValueError("receipt version chain hash does not match predecessor")
        state = LotBasisTransferReceiptState(
            source_transaction_id=str(record.source_transaction_id),
            target_transaction_id=str(record.target_transaction_id),
            target_lot_id=str(record.target_lot_id),
            portfolio_id=str(record.portfolio_id),
            source_instrument_id=str(record.source_instrument_id),
            source_security_id=str(record.source_security_id),
            target_instrument_id=cast(str | None, record.target_instrument_id),
            transfer_timestamp=record.transfer_timestamp,
            transaction_type=str(record.transaction_type),
            cost_basis_method=CostBasisMethod(str(record.cost_basis_method)),
            calculation_policy_id=cast(str | None, record.calculation_policy_id),
            calculation_policy_version=cast(str | None, record.calculation_policy_version),
            transaction_calculation_lineage=required_calculation_lineage(
                record.transaction_calculation_lineage,
                "transaction calculation lineage",
            ),
            status=LotBasisTransferReceiptStatus(str(record.status)),
            transferred_cost_local=record.transferred_cost_local,
            transferred_cost_base=record.transferred_cost_base,
            allocations=tuple(_verified_allocation(record, item) for item in allocations),
            basis_transfer_calculation_lineage=(
                required_calculation_lineage(
                    record.basis_transfer_calculation_lineage,
                    "basis-transfer calculation lineage",
                )
                if record.basis_transfer_calculation_lineage is not None
                else None
            ),
            void_reason=cast(str | None, record.void_reason),
        )
        if int(record.allocation_count) != state.allocation_count:
            raise ValueError("receipt allocation count does not match child rows")
        if str(record.receipt_id) != state.receipt_id:
            raise ValueError("receipt identity does not match reconstructed scope")
        if str(record.semantic_content_hash) != state.semantic_content_hash:
            raise ValueError("receipt semantic hash does not match reconstructed content")
        expected_receipt_hash = _receipt_content_hash(
            state=state,
            receipt_version=version,
            previous_receipt_content_hash=previous_hash,
        )
        if str(record.receipt_content_hash) != expected_receipt_hash:
            raise ValueError("receipt content hash does not match reconstructed version")
        return state
    except (TypeError, ValueError) as exc:
        raise CorruptLotBasisTransferReceiptError(
            f"persisted lot basis-transfer receipt is corrupt: {record.receipt_id}"
        ) from exc


def _verified_allocation(
    receipt: LotBasisTransferReceiptRecord,
    record: LotBasisTransferAllocationRecord,
) -> SourceLotBasisTransferAllocation:
    if str(record.portfolio_id) != str(receipt.portfolio_id) or str(
        record.source_security_id
    ) != str(receipt.source_security_id):
        raise ValueError("allocation scope differs from receipt scope")
    allocation = SourceLotBasisTransferAllocation(
        allocation_ordinal=int(record.allocation_ordinal),
        source_lot_id=str(record.source_lot_id),
        source_transaction_id=str(record.source_transaction_id),
        source_acquisition_date=record.source_acquisition_date,
        retained_quantity=record.retained_quantity,
        source_cost_local_before=record.source_cost_local_before,
        source_cost_base_before=record.source_cost_base_before,
        transferred_cost_local=record.transferred_cost_local,
        transferred_cost_base=record.transferred_cost_base,
        retained_cost_local=record.retained_cost_local,
        retained_cost_base=record.retained_cost_base,
    )
    expected_hash = _allocation_content_hash(
        receipt_id=str(receipt.receipt_id),
        allocation=allocation,
    )
    if str(record.allocation_content_hash) != expected_hash:
        raise ValueError("allocation content hash does not match reconstructed content")
    return allocation


def _require_same_receipt_identity(
    existing: LotBasisTransferReceiptState,
    candidate: LotBasisTransferReceiptState,
) -> None:
    if (
        existing.receipt_id != candidate.receipt_id
        or existing.source_transaction_id != candidate.source_transaction_id
        or existing.portfolio_id != candidate.portfolio_id
        or existing.source_security_id != candidate.source_security_id
    ):
        raise CorruptLotBasisTransferReceiptError("receipt identity changed across versions")


def _header_values(
    *,
    state: LotBasisTransferReceiptState,
    receipt_version: int,
    previous_receipt_content_hash: str | None,
    receipt_content_hash: str,
) -> dict[str, object]:
    return {
        "allocation_count": state.allocation_count,
        "basis_transfer_calculation_lineage": (
            state.basis_transfer_calculation_lineage.lineage_payload()
            if state.basis_transfer_calculation_lineage is not None
            else None
        ),
        "calculation_policy_id": state.calculation_policy_id,
        "calculation_policy_version": state.calculation_policy_version,
        "cost_basis_method": state.cost_basis_method.value,
        "portfolio_id": state.portfolio_id,
        "previous_receipt_content_hash": previous_receipt_content_hash,
        "receipt_content_hash": receipt_content_hash,
        "receipt_id": state.receipt_id,
        "receipt_version": receipt_version,
        "semantic_content_hash": state.semantic_content_hash,
        "source_instrument_id": state.source_instrument_id,
        "source_security_id": state.source_security_id,
        "source_transaction_id": state.source_transaction_id,
        "status": state.status.value,
        "target_instrument_id": state.target_instrument_id,
        "target_lot_id": state.target_lot_id,
        "target_transaction_id": state.target_transaction_id,
        "transaction_calculation_lineage": (
            state.transaction_calculation_lineage.lineage_payload()
        ),
        "transaction_type": state.transaction_type,
        "transfer_timestamp": state.transfer_timestamp,
        "transferred_cost_base": state.transferred_cost_base,
        "transferred_cost_local": state.transferred_cost_local,
        "void_reason": state.void_reason,
    }


def _allocation_values(
    *,
    state: LotBasisTransferReceiptState,
    receipt_version: int,
) -> list[dict[str, object]]:
    return [
        {
            "allocation_content_hash": _allocation_content_hash(
                receipt_id=state.receipt_id,
                allocation=allocation,
            ),
            "allocation_ordinal": allocation.allocation_ordinal,
            "portfolio_id": state.portfolio_id,
            "receipt_id": state.receipt_id,
            "receipt_version": receipt_version,
            "retained_cost_base": allocation.retained_cost_base,
            "retained_cost_local": allocation.retained_cost_local,
            "retained_quantity": allocation.retained_quantity,
            "source_acquisition_date": allocation.source_acquisition_date,
            "source_cost_base_before": allocation.source_cost_base_before,
            "source_cost_local_before": allocation.source_cost_local_before,
            "source_lot_id": allocation.source_lot_id,
            "source_security_id": state.source_security_id,
            "source_transaction_id": allocation.source_transaction_id,
            "transferred_cost_base": allocation.transferred_cost_base,
            "transferred_cost_local": allocation.transferred_cost_local,
        }
        for allocation in state.allocations
    ]


def _receipt_content_hash(
    *,
    state: LotBasisTransferReceiptState,
    receipt_version: int,
    previous_receipt_content_hash: str | None,
) -> str:
    return cast(
        str,
        receipt_version_content_hash(
            receipt_id=state.receipt_id,
            semantic_content_hash=state.semantic_content_hash,
            receipt_version=receipt_version,
            previous_receipt_content_hash=previous_receipt_content_hash,
        ),
    )


def _allocation_content_hash(
    *,
    receipt_id: str,
    allocation: SourceLotBasisTransferAllocation,
) -> str:
    payload = {
        "allocation_ordinal": allocation.allocation_ordinal,
        "retained_cost_base": allocation.retained_cost_base,
        "retained_cost_local": allocation.retained_cost_local,
        "retained_quantity": allocation.retained_quantity,
        "source_acquisition_date": allocation.source_acquisition_date,
        "source_cost_base_before": allocation.source_cost_base_before,
        "source_cost_local_before": allocation.source_cost_local_before,
        "source_lot_id": allocation.source_lot_id,
        "source_transaction_id": allocation.source_transaction_id,
        "transferred_cost_base": allocation.transferred_cost_base,
        "transferred_cost_local": allocation.transferred_cost_local,
    }
    return cast(
        str,
        cost_basis_allocation_content_hash(
            receipt_id=receipt_id,
            payload=payload,
        ),
    )
