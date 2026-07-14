"""Define framework-neutral cost-basis checkpoint and persistence records."""

from dataclasses import dataclass
from decimal import Decimal

from ...domain.cost_basis import AverageCostPoolCheckpoint
from ...domain.transaction import BookedTransaction


@dataclass(frozen=True, slots=True)
class OpenLotCheckpointRecord:
    """Carry one persisted open-lot state with its canonical source transaction."""

    transaction: BookedTransaction
    quantity: Decimal
    cost_local: Decimal
    cost_base: Decimal


@dataclass(frozen=True, slots=True)
class AverageCostPoolCheckpointRecord:
    """Carry an AVCO aggregate checkpoint and optional representative transaction."""

    checkpoint: AverageCostPoolCheckpoint
    representative_transaction: BookedTransaction | None


@dataclass(frozen=True, slots=True)
class AverageCostPoolPersistedSummary:
    """Summarize persisted AVCO source and aggregate state for reconciliation."""

    source_count: int
    source_quantity: Decimal
    source_cost_local: Decimal
    source_cost_base: Decimal
    pool_quantity: Decimal | None
    pool_cost_local: Decimal | None
    pool_cost_base: Decimal | None
