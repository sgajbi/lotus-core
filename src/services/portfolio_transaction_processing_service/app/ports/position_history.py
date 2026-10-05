"""Define framework-neutral ports for position-history materialization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from ..domain import BookedTransaction, PositionHistoryRecord, PositionRecalculationState
from ..domain.transaction.semantic_identity import (
    TransactionSemanticIdentity,
    build_transaction_correction_identity,
    build_transaction_semantic_identity,
)


class PositionRecalculationReason(StrEnum):
    """Classify position recalculation coordination decisions."""

    ALREADY_MATERIALIZED = "already_materialized"
    BACKDATED_TRANSACTION = "backdated_transaction"
    STALE_EPOCH = "stale_epoch"


class PositionReplayMode(StrEnum):
    """Classify position replay work-depth observations."""

    COALESCED = "coalesced"
    INLINE_REBUILD = "inline_rebuild"


@dataclass(frozen=True, slots=True)
class PositionMaterializationProgress:
    """Carry epoch-scoped history and completed-snapshot progress."""

    latest_history_date: date | None
    latest_completed_snapshot_date: date | None


@dataclass(frozen=True, slots=True)
class PositionReplayWindow:
    """Carry the position anchor and ordered transactions for one replay window."""

    anchor: PositionHistoryRecord | None
    transactions: tuple[BookedTransaction, ...]


@dataclass(frozen=True, slots=True)
class MaterializedPositionReceipt:
    """Carry one matching history row protected by retained state and history locks."""

    tenant_id: str
    portfolio_id: str
    security_id: str
    transaction_id: str
    epoch: int
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class AdmittedPositionCorrectionGroup:
    """Retain one accepted command and its complete immutable cost-stage outputs."""

    root_transaction: BookedTransaction
    admission_identity: TransactionSemanticIdentity
    event_id: str
    repair_delivery_id: str | None
    correction_claimed: bool
    repair_claimed: bool
    members: tuple[BookedTransaction, ...]
    replay_epoch: int | None = None
    active_transaction_id: str | None = None

    def __post_init__(self) -> None:
        root = self.root_transaction
        if not root.tenant_id or not root.tenant_id.strip() or not self.event_id.strip():
            raise ValueError("Admitted position group requires tenant and event authority")
        if not (self.correction_claimed or self.repair_claimed):
            raise ValueError("Admitted position group requires a claimed correction or repair")
        correction_identity = build_transaction_correction_identity(root)
        expected = (
            (correction_identity,)
            if self.correction_claimed
            else (build_transaction_semantic_identity(root), correction_identity)
        )
        if self.admission_identity not in expected:
            raise ValueError("Admitted position group has conflicting root identity")
        identifiers = tuple(member.transaction_id for member in self.members)
        if len(set(identifiers)) != len(identifiers) or identifiers.count(root.transaction_id) != 1:
            raise ValueError("Admitted position group requires unique members and one root")
        if self.active_transaction_id is not None and self.active_transaction_id not in identifiers:
            raise ValueError("Admitted position group has an unknown active member")
        for member in self.members:
            if member.portfolio_id != root.portfolio_id or member.tenant_id not in {
                None,
                root.tenant_id,
            }:
                raise ValueError(
                    "Admitted position group has conflicting member scope: "
                    f"root={(root.tenant_id, root.portfolio_id, root.transaction_id)!r}, "
                    f"member={(member.tenant_id, member.portfolio_id, member.transaction_id)!r}"
                )
            if member.epoch != root.epoch:
                raise ValueError("Admitted position group has conflicting source epoch")
            if member.transaction_id == root.transaction_id:
                if member.tenant_id != root.tenant_id:
                    raise ValueError("Admitted position group has conflicting root tenant")
                if build_transaction_semantic_identity(member) != (
                    build_transaction_semantic_identity(root)
                ):
                    raise ValueError("Admitted position group has conflicting root material")
            elif member.originating_transaction_id != root.transaction_id:
                raise ValueError("Admitted position group has unrelated generated membership")
            elif member.tenant_id is None and member.calculation_lineage is None:
                raise ValueError("Admitted position group requires generated output lineage")

    def require_member(self, transaction: BookedTransaction) -> None:
        if transaction not in self.members:
            raise ValueError("Position input is not an exact admitted cost-result member")


class PositionHistoryRepository(Protocol):
    """Load and persist canonical transaction-backed position history."""

    async def load_materialization_progress(
        self, *, portfolio_id: str, security_id: str, epoch: int
    ) -> PositionMaterializationProgress: ...

    async def load_materialized_receipt(
        self, transaction: BookedTransaction, *, expected_epoch: int
    ) -> MaterializedPositionReceipt | None:
        """Retain exact current state/history locks or return no authority."""
        ...

    async def acquire_replay_lock(
        self, *, portfolio_id: str, security_id: str, epoch: int
    ) -> None: ...

    async def list_all_transactions(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        admitted_correction: AdmittedPositionCorrectionGroup | None = None,
    ) -> tuple[BookedTransaction, ...]: ...

    async def load_replay_window(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        position_date: date,
        epoch: int,
        admitted_correction: AdmittedPositionCorrectionGroup | None = None,
    ) -> PositionReplayWindow: ...

    async def delete_records_from(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        position_date: date,
        epoch: int,
    ) -> int: ...

    async def save_records(self, records: tuple[PositionHistoryRecord, ...]) -> None: ...


class PositionRecalculationStateStore(Protocol):
    """Coordinate position dirty windows and compare-and-set epochs."""

    async def get_or_create(
        self, *, portfolio_id: str, security_id: str
    ) -> PositionRecalculationState: ...

    async def advance_epoch(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        expected_epoch: int,
        watermark_date: date,
    ) -> PositionRecalculationState | None: ...

    async def rearm_generation(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        expected_epoch: int,
        watermark_date: date,
    ) -> bool: ...


class PositionHistoryObserver(Protocol):
    """Observe position recalculation without coupling application policy to telemetry."""

    def stale_epoch_discarded(
        self,
        *,
        transaction: BookedTransaction,
        current_epoch: int,
    ) -> None: ...

    def backdated_recalculation_detected(
        self,
        *,
        transaction: BookedTransaction,
        current_state: PositionRecalculationState,
        effective_completed_date: date,
        latest_history_date: date | None,
    ) -> None: ...

    def recalculation_coalesced(
        self,
        *,
        transaction: BookedTransaction,
        epoch: int,
        reason: PositionRecalculationReason,
    ) -> None: ...

    def epoch_advanced(
        self,
        *,
        transaction: BookedTransaction,
        state: PositionRecalculationState,
    ) -> None: ...

    def replay_work_items(self, *, mode: PositionReplayMode, count: int) -> None: ...

    def history_rebuilt(
        self,
        *,
        transaction: BookedTransaction,
        epoch: int,
        record_count: int,
        earliest_transaction_date: date,
    ) -> None: ...

    def records_staged(self, *, epoch: int, record_count: int) -> None: ...

    def generation_rearmed(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        epoch: int,
        transaction_date: date,
        watermark_date: date,
    ) -> None: ...
