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
    canonical_content_hash,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.domain.cost_basis_receipt_integrity import (
    verify_cost_basis_receipt_version_chain,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cost_basis import (
    AmortizedCostAllocationEvidence,
    LotDisposalDestination,
    LotDisposalDestinationType,
    LotDisposalReceiptState,
    LotDisposalReceiptStatus,
    SourceLotDisposalAllocation,
)
from ...domain.cost_basis.calculation.disposal_allocation import (
    source_lot_disposal_allocation_payload,
)
from ...domain.cost_basis.state_lineage import canonical_cost_basis_output_payload
from .receipt_integrity import receipt_version_content_hash, required_calculation_lineage


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
        chains = await self._load_receipt_chains(transaction_ids)
        persisted_records = tuple(record for chain in chains.values() for record in chain)
        persisted_allocations = await self._load_allocations(persisted_records)
        latest: dict[str, LotDisposalReceiptRecord] = {}
        verified_latest: dict[str, LotDisposalReceiptState] = {}
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
                raise CorruptLotDisposalReceiptError(
                    f"persisted lot-disposal receipt is corrupt: {transaction_id}"
                ) from exc
            latest[transaction_id] = chain[-1]
            verified_latest[transaction_id] = verified_states[-1]

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
                    if prior_state.semantic_payload() != state.semantic_payload():
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

    async def _load_receipt_chains(
        self,
        transaction_ids: tuple[str, ...],
    ) -> dict[str, tuple[LotDisposalReceiptRecord, ...]]:
        record = LotDisposalReceiptRecord
        rows = (
            await self._session.scalars(
                select(record)
                .where(record.disposal_transaction_id.in_(transaction_ids))
                .order_by(record.disposal_transaction_id, record.receipt_version)
            )
        ).all()
        grouped: defaultdict[str, list[LotDisposalReceiptRecord]] = defaultdict(list)
        for row in rows:
            grouped[str(row.disposal_transaction_id)].append(row)
        return {transaction_id: tuple(items) for transaction_id, items in grouped.items()}

    async def _load_allocations(
        self,
        receipts: tuple[LotDisposalReceiptRecord, ...],
    ) -> dict[tuple[str, int], tuple[LotDisposalAllocationRecord, ...]]:
        receipt_ids = {str(record.receipt_id) for record in receipts}
        if not receipt_ids:
            return {}
        allocation = LotDisposalAllocationRecord
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
            transaction_calculation_lineage=required_calculation_lineage(
                record.transaction_calculation_lineage,
                "transaction calculation lineage",
            ),
            status=LotDisposalReceiptStatus(str(record.status)),
            consumed_quantity=record.consumed_quantity,
            consumed_cost_local=record.consumed_cost_local,
            consumed_cost_base=record.consumed_cost_base,
            allocations=tuple(_verified_allocation(record, item) for item in allocations),
            disposal_calculation_lineage=(
                required_calculation_lineage(
                    record.disposal_calculation_lineage,
                    "disposal calculation lineage",
                )
                if record.disposal_calculation_lineage is not None
                else None
            ),
            destination=_destination_from_record(record),
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


def _destination_from_record(
    record: LotDisposalReceiptRecord,
) -> LotDisposalDestination | None:
    destination_values = (
        record.destination_type,
        record.target_transaction_id,
        record.target_lot_id,
        record.target_instrument_id,
        record.external_destination_reference,
    )
    if all(value is None for value in destination_values):
        return None
    if record.destination_type is None:
        raise ValueError("lot-disposal destination discriminator is missing")
    return LotDisposalDestination(
        destination_type=LotDisposalDestinationType(str(record.destination_type)),
        target_transaction_id=cast(str | None, record.target_transaction_id),
        target_lot_id=cast(str | None, record.target_lot_id),
        target_instrument_id=cast(str | None, record.target_instrument_id),
        external_destination_reference=cast(
            str | None,
            record.external_destination_reference,
        ),
    )


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
        amortized_cost_evidence=_amortized_cost_evidence(receipt, record),
    )
    expected_hash = _allocation_content_hash(
        receipt_id=str(receipt.receipt_id),
        allocation=allocation,
    )
    if str(record.allocation_content_hash) != expected_hash:
        raise ValueError("allocation content hash does not match reconstructed content")
    return allocation


def _amortized_cost_evidence(
    receipt: LotDisposalReceiptRecord,
    record: LotDisposalAllocationRecord,
) -> AmortizedCostAllocationEvidence | None:
    field_names = (
        "amortized_cost_profile_id",
        "amortized_cost_profile_version",
        "amortized_cost_profile_content_hash",
        "amortized_cost_currency",
        "amortized_cost_recognized_through",
        "amortized_cost_original_quantity",
        "amortized_cost_open_quantity_before",
        "amortized_cost_residual_quantity",
        "amortized_cost_scheduled_local",
        "amortized_cost_current_local",
        "amortized_cost_current_base",
        "amortized_cost_residual_local",
        "amortized_cost_book_fx_rate_to_base",
        "amortized_cost_residual_base",
        "amortized_cost_retained_rounding_local",
        "amortized_cost_retained_rounding_base",
        "amortized_cost_calculation_lineage",
    )
    values = tuple(getattr(record, field_name) for field_name in field_names)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("amortized-cost allocation evidence is only partially persisted")
    return AmortizedCostAllocationEvidence(
        profile_id=str(record.amortized_cost_profile_id),
        profile_version=int(record.amortized_cost_profile_version),
        profile_content_hash=str(record.amortized_cost_profile_content_hash),
        currency=str(record.amortized_cost_currency),
        disposal_date=receipt.disposal_timestamp.date(),
        recognized_through_date=record.amortized_cost_recognized_through,
        original_quantity=record.amortized_cost_original_quantity,
        open_quantity_before=record.amortized_cost_open_quantity_before,
        consumed_quantity=record.consumed_quantity,
        residual_quantity=record.amortized_cost_residual_quantity,
        scheduled_cost_local=record.amortized_cost_scheduled_local,
        current_cost_local=record.amortized_cost_current_local,
        current_cost_base=record.amortized_cost_current_base,
        consumed_cost_local=record.consumed_cost_local,
        residual_cost_local=record.amortized_cost_residual_local,
        book_cost_fx_rate_to_base=record.amortized_cost_book_fx_rate_to_base,
        consumed_cost_base=record.consumed_cost_base,
        residual_cost_base=record.amortized_cost_residual_base,
        retained_rounding_residual_local=(record.amortized_cost_retained_rounding_local),
        retained_rounding_residual_base=record.amortized_cost_retained_rounding_base,
        calculation_lineage=required_calculation_lineage(
            record.amortized_cost_calculation_lineage,
            "amortized-cost allocation calculation lineage",
        ),
    )


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
    destination = state.destination
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
        "destination_type": (
            destination.destination_type.value if destination is not None else None
        ),
        "external_destination_reference": (
            destination.external_destination_reference if destination is not None else None
        ),
        "instrument_id": state.instrument_id,
        "portfolio_id": state.portfolio_id,
        "previous_receipt_content_hash": previous_receipt_content_hash,
        "receipt_content_hash": receipt_content_hash,
        "receipt_id": state.receipt_id,
        "receipt_version": receipt_version,
        "security_id": state.security_id,
        "semantic_content_hash": state.semantic_content_hash,
        "status": state.status.value,
        "target_instrument_id": (
            destination.target_instrument_id if destination is not None else None
        ),
        "target_lot_id": destination.target_lot_id if destination is not None else None,
        "target_transaction_id": (
            destination.target_transaction_id if destination is not None else None
        ),
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
    values: list[dict[str, object]] = []
    for allocation in state.allocations:
        evidence = allocation.amortized_cost_evidence
        values.append(
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
                "amortized_cost_profile_id": evidence.profile_id if evidence is not None else None,
                "amortized_cost_profile_version": (
                    evidence.profile_version if evidence is not None else None
                ),
                "amortized_cost_profile_content_hash": (
                    evidence.profile_content_hash if evidence is not None else None
                ),
                "amortized_cost_currency": evidence.currency if evidence is not None else None,
                "amortized_cost_recognized_through": (
                    evidence.recognized_through_date if evidence is not None else None
                ),
                "amortized_cost_original_quantity": (
                    evidence.original_quantity if evidence is not None else None
                ),
                "amortized_cost_open_quantity_before": (
                    evidence.open_quantity_before if evidence is not None else None
                ),
                "amortized_cost_residual_quantity": (
                    evidence.residual_quantity if evidence is not None else None
                ),
                "amortized_cost_scheduled_local": (
                    evidence.scheduled_cost_local if evidence is not None else None
                ),
                "amortized_cost_current_local": (
                    evidence.current_cost_local if evidence is not None else None
                ),
                "amortized_cost_current_base": (
                    evidence.current_cost_base if evidence is not None else None
                ),
                "amortized_cost_residual_local": (
                    evidence.residual_cost_local if evidence is not None else None
                ),
                "amortized_cost_book_fx_rate_to_base": (
                    evidence.book_cost_fx_rate_to_base if evidence is not None else None
                ),
                "amortized_cost_residual_base": (
                    evidence.residual_cost_base if evidence is not None else None
                ),
                "amortized_cost_retained_rounding_local": (
                    evidence.retained_rounding_residual_local if evidence is not None else None
                ),
                "amortized_cost_retained_rounding_base": (
                    evidence.retained_rounding_residual_base if evidence is not None else None
                ),
                "amortized_cost_calculation_lineage": (
                    evidence.calculation_lineage.lineage_payload() if evidence is not None else None
                ),
            }
        )
    return values


def _receipt_content_hash(
    *,
    state: LotDisposalReceiptState,
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
    allocation: SourceLotDisposalAllocation,
) -> str:
    payload: dict[str, Any] = {
        **source_lot_disposal_allocation_payload(allocation),
        "receipt_id": receipt_id,
    }
    return cast(
        str,
        canonical_content_hash(canonical_cost_basis_output_payload(payload)),
    )
