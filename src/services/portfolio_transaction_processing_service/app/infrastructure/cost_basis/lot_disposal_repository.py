"""SQLAlchemy adapter for immutable versioned lot-disposal receipts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any, cast

from portfolio_common.database_models import (
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
)
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    calculation_lineage_from_payload,
    canonical_content_hash,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cost_basis import (
    LotDisposalReceiptState,
    LotDisposalReceiptStatus,
    SourceLotDisposalAllocation,
)
from ...domain.cost_basis.state_lineage import canonical_cost_basis_output_payload


class CorruptLotDisposalReceiptError(ValueError):
    """Raised when persisted receipt evidence fails deterministic reconstruction."""


class ConflictingLotDisposalReceiptError(ValueError):
    """Raised when a concurrent or malformed version collides during append."""


class SqlAlchemyCostBasisLotDisposalRepository:
    """Append correction versions and classify exact receipt replays as neutral."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reconcile_disposal_receipts(
        self,
        *,
        receipt_states: tuple[LotDisposalReceiptState, ...],
    ) -> None:
        """Append changed ACTIVE/VOIDED states under the caller's stream lock."""

        if not receipt_states:
            return
        _validate_candidate_batch(receipt_states)
        transaction_ids = tuple(state.disposal_transaction_id for state in receipt_states)
        latest = await self._load_latest_receipts(transaction_ids)
        latest_allocations = await self._load_allocations(tuple(latest.values()))
        previous = await self._load_previous_receipts(tuple(latest.values()))
        verified_latest = {
            transaction_id: _verified_state(
                record,
                allocations=latest_allocations.get(
                    (record.receipt_id, record.receipt_version),
                    (),
                ),
                previous_record=previous.get((record.receipt_id, record.receipt_version - 1)),
            )
            for transaction_id, record in latest.items()
        }

        header_values: list[dict[str, object]] = []
        allocation_values: list[dict[str, object]] = []
        for state in receipt_states:
            prior_record = latest.get(state.disposal_transaction_id)
            prior_state = verified_latest.get(state.disposal_transaction_id)
            if prior_record is None:
                if state.status is LotDisposalReceiptStatus.VOIDED:
                    continue
                receipt_version = 1
                previous_hash = None
            else:
                if prior_state is None:
                    raise CorruptLotDisposalReceiptError(
                        f"latest receipt state was not verified: {state.receipt_id}"
                    )
                _require_same_receipt_identity(prior_state, state)
                if prior_state.semantic_content_hash == state.semantic_content_hash:
                    if prior_state != state:
                        raise CorruptLotDisposalReceiptError(
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
                _allocation_values(
                    state=state,
                    receipt_version=receipt_version,
                )
            )

        if not header_values:
            return
        try:
            await self._session.execute(pg_insert(LotDisposalReceiptRecord).values(header_values))
            if allocation_values:
                await self._session.execute(
                    pg_insert(LotDisposalAllocationRecord).values(allocation_values)
                )
        except IntegrityError as exc:
            raise ConflictingLotDisposalReceiptError(
                "lot-disposal receipt version collided during append"
            ) from exc

    async def _load_latest_receipts(
        self,
        transaction_ids: tuple[str, ...],
    ) -> dict[str, LotDisposalReceiptRecord]:
        record = LotDisposalReceiptRecord
        latest_versions = (
            select(
                record.disposal_transaction_id.label("disposal_transaction_id"),
                func.max(record.receipt_version).label("receipt_version"),
            )
            .where(record.disposal_transaction_id.in_(transaction_ids))
            .group_by(record.disposal_transaction_id)
            .subquery()
        )
        rows = (
            await self._session.scalars(
                select(record).join(
                    latest_versions,
                    and_(
                        record.disposal_transaction_id == latest_versions.c.disposal_transaction_id,
                        record.receipt_version == latest_versions.c.receipt_version,
                    ),
                )
            )
        ).all()
        return {str(row.disposal_transaction_id): row for row in rows}

    async def _load_previous_receipts(
        self,
        latest: tuple[LotDisposalReceiptRecord, ...],
    ) -> dict[tuple[str, int], LotDisposalReceiptRecord]:
        identities = [
            (str(record.receipt_id), int(record.receipt_version) - 1)
            for record in latest
            if int(record.receipt_version) > 1
        ]
        if not identities:
            return {}
        record = LotDisposalReceiptRecord
        rows = (
            await self._session.scalars(
                select(record).where(
                    tuple_(record.receipt_id, record.receipt_version).in_(identities)
                )
            )
        ).all()
        return {(str(row.receipt_id), int(row.receipt_version)): row for row in rows}

    async def _load_allocations(
        self,
        latest: tuple[LotDisposalReceiptRecord, ...],
    ) -> dict[tuple[str, int], tuple[LotDisposalAllocationRecord, ...]]:
        identities = [(str(record.receipt_id), int(record.receipt_version)) for record in latest]
        if not identities:
            return {}
        allocation = LotDisposalAllocationRecord
        rows = (
            await self._session.scalars(
                select(allocation)
                .where(tuple_(allocation.receipt_id, allocation.receipt_version).in_(identities))
                .order_by(
                    allocation.receipt_id,
                    allocation.receipt_version,
                    allocation.allocation_ordinal,
                )
            )
        ).all()
        grouped: defaultdict[tuple[str, int], list[LotDisposalAllocationRecord]] = defaultdict(list)
        for row in rows:
            grouped[(str(row.receipt_id), int(row.receipt_version))].append(row)
        return {identity: tuple(items) for identity, items in grouped.items()}


def _validate_candidate_batch(receipt_states: Sequence[LotDisposalReceiptState]) -> None:
    if not all(isinstance(state, LotDisposalReceiptState) for state in receipt_states):
        raise TypeError("receipt_states must contain LotDisposalReceiptState values")
    receipt_ids = [state.receipt_id for state in receipt_states]
    transaction_ids = [state.disposal_transaction_id for state in receipt_states]
    if len(set(receipt_ids)) != len(receipt_ids):
        raise ValueError("receipt batch contains duplicate receipt identities")
    if len(set(transaction_ids)) != len(transaction_ids):
        raise ValueError("receipt batch contains duplicate transaction identities")


def _verified_state(
    record: LotDisposalReceiptRecord,
    *,
    allocations: Sequence[LotDisposalAllocationRecord],
    previous_record: LotDisposalReceiptRecord | None,
) -> LotDisposalReceiptState:
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
        state = LotDisposalReceiptState(
            disposal_transaction_id=str(record.disposal_transaction_id),
            portfolio_id=str(record.portfolio_id),
            instrument_id=str(record.instrument_id),
            security_id=str(record.security_id),
            disposal_timestamp=record.disposal_timestamp,
            transaction_type=str(record.transaction_type),
            cost_basis_method=CostBasisMethod(str(record.cost_basis_method)),
            calculation_policy_id=cast(str | None, record.calculation_policy_id),
            calculation_policy_version=cast(str | None, record.calculation_policy_version),
            transaction_calculation_lineage=_required_lineage(
                record.transaction_calculation_lineage,
                "transaction calculation lineage",
            ),
            status=LotDisposalReceiptStatus(str(record.status)),
            consumed_quantity=record.consumed_quantity,
            consumed_cost_local=record.consumed_cost_local,
            consumed_cost_base=record.consumed_cost_base,
            allocations=tuple(_verified_allocation(record, item) for item in allocations),
            disposal_calculation_lineage=(
                _required_lineage(
                    record.disposal_calculation_lineage,
                    "disposal calculation lineage",
                )
                if record.disposal_calculation_lineage is not None
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
        raise CorruptLotDisposalReceiptError(
            f"persisted lot-disposal receipt is corrupt: {record.receipt_id}"
        ) from exc


def _verified_allocation(
    receipt: LotDisposalReceiptRecord,
    record: LotDisposalAllocationRecord,
) -> SourceLotDisposalAllocation:
    if str(record.portfolio_id) != str(receipt.portfolio_id) or str(record.security_id) != str(
        receipt.security_id
    ):
        raise ValueError("allocation scope differs from receipt scope")
    allocation = SourceLotDisposalAllocation(
        source_lot_id=str(record.source_lot_id),
        source_transaction_id=str(record.source_transaction_id),
        source_acquisition_date=record.source_acquisition_date,
        allocation_ordinal=int(record.allocation_ordinal),
        consumed_quantity=record.consumed_quantity,
        consumed_cost_local=record.consumed_cost_local,
        consumed_cost_base=record.consumed_cost_base,
    )
    expected_hash = _allocation_content_hash(
        receipt_id=str(receipt.receipt_id),
        allocation=allocation,
    )
    if str(record.allocation_content_hash) != expected_hash:
        raise ValueError("allocation content hash does not match reconstructed content")
    return allocation


def _required_lineage(payload: object, context: str) -> CalculationLineage:
    lineage = calculation_lineage_from_payload(payload)
    if lineage is None:
        raise ValueError(f"{context} is required")
    return lineage


def _require_same_receipt_identity(
    existing: LotDisposalReceiptState,
    candidate: LotDisposalReceiptState,
) -> None:
    if (
        existing.receipt_id != candidate.receipt_id
        or existing.disposal_transaction_id != candidate.disposal_transaction_id
        or existing.portfolio_id != candidate.portfolio_id
        or existing.security_id != candidate.security_id
    ):
        raise CorruptLotDisposalReceiptError("receipt identity changed across versions")


def _header_values(
    *,
    state: LotDisposalReceiptState,
    receipt_version: int,
    previous_receipt_content_hash: str | None,
    receipt_content_hash: str,
) -> dict[str, object]:
    return {
        "allocation_count": state.allocation_count,
        "calculation_policy_id": state.calculation_policy_id,
        "calculation_policy_version": state.calculation_policy_version,
        "consumed_cost_base": state.consumed_cost_base,
        "consumed_cost_local": state.consumed_cost_local,
        "consumed_quantity": state.consumed_quantity,
        "cost_basis_method": state.cost_basis_method.value,
        "disposal_calculation_lineage": (
            state.disposal_calculation_lineage.lineage_payload()
            if state.disposal_calculation_lineage is not None
            else None
        ),
        "disposal_timestamp": state.disposal_timestamp,
        "disposal_transaction_id": state.disposal_transaction_id,
        "instrument_id": state.instrument_id,
        "portfolio_id": state.portfolio_id,
        "previous_receipt_content_hash": previous_receipt_content_hash,
        "receipt_content_hash": receipt_content_hash,
        "receipt_id": state.receipt_id,
        "receipt_version": receipt_version,
        "security_id": state.security_id,
        "semantic_content_hash": state.semantic_content_hash,
        "status": state.status.value,
        "transaction_calculation_lineage": (
            state.transaction_calculation_lineage.lineage_payload()
        ),
        "transaction_type": state.transaction_type,
        "void_reason": state.void_reason,
    }


def _allocation_values(
    *,
    state: LotDisposalReceiptState,
    receipt_version: int,
) -> list[dict[str, object]]:
    return [
        {
            "allocation_content_hash": _allocation_content_hash(
                receipt_id=state.receipt_id,
                allocation=allocation,
            ),
            "allocation_ordinal": allocation.allocation_ordinal,
            "consumed_cost_base": allocation.consumed_cost_base,
            "consumed_cost_local": allocation.consumed_cost_local,
            "consumed_quantity": allocation.consumed_quantity,
            "portfolio_id": state.portfolio_id,
            "receipt_id": state.receipt_id,
            "receipt_version": receipt_version,
            "security_id": state.security_id,
            "source_acquisition_date": allocation.source_acquisition_date,
            "source_lot_id": allocation.source_lot_id,
            "source_transaction_id": allocation.source_transaction_id,
        }
        for allocation in state.allocations
    ]


def _receipt_content_hash(
    *,
    state: LotDisposalReceiptState,
    receipt_version: int,
    previous_receipt_content_hash: str | None,
) -> str:
    return cast(
        str,
        canonical_content_hash(
            {
                "previous_receipt_content_hash": previous_receipt_content_hash,
                "receipt_id": state.receipt_id,
                "receipt_version": receipt_version,
                "semantic_content_hash": state.semantic_content_hash,
            }
        ),
    )


def _allocation_content_hash(
    *,
    receipt_id: str,
    allocation: SourceLotDisposalAllocation,
) -> str:
    payload: dict[str, Any] = {
        "allocation_ordinal": allocation.allocation_ordinal,
        "consumed_cost_base": allocation.consumed_cost_base,
        "consumed_cost_local": allocation.consumed_cost_local,
        "consumed_quantity": allocation.consumed_quantity,
        "receipt_id": receipt_id,
        "source_acquisition_date": allocation.source_acquisition_date,
        "source_lot_id": allocation.source_lot_id,
        "source_transaction_id": allocation.source_transaction_id,
    }
    return cast(
        str,
        canonical_content_hash(canonical_cost_basis_output_payload(payload)),
    )
