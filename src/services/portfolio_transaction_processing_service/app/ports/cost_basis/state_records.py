"""Define framework-neutral cost-basis checkpoint and persistence records."""

from dataclasses import dataclass
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import CalculationLineage

from ...domain.cost_basis import AmortizedCostCarryState, AverageCostPoolCheckpoint
from ...domain.transaction import BookedTransaction


@dataclass(frozen=True, slots=True)
class OpenLotCheckpointRecord:
    """Carry one persisted open-lot state with its canonical source transaction."""

    transaction: BookedTransaction
    original_quantity: Decimal
    quantity: Decimal
    cost_local: Decimal
    cost_base: Decimal
    amortized_cost: AmortizedCostCarryState | None = None


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
    source_lineage_valid: bool
    pool_quantity: Decimal | None
    pool_cost_local: Decimal | None
    pool_cost_base: Decimal | None
    pool_instrument_id: str | None
    pool_representative_source_transaction_id: str | None
    pool_state_version: str | None
    pool_calculation_lineage: CalculationLineage | None
