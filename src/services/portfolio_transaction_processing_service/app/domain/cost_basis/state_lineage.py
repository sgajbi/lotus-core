"""Build deterministic lineage at durable cost-basis state boundaries."""

from collections.abc import Mapping
from dataclasses import dataclass

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    canonical_cost_basis_output_payload,
)
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1


@dataclass(frozen=True, slots=True)
class CostBasisStateTransitionEvidence:
    """Identify the calculated transaction that caused a lot-state transition."""

    trigger_transaction_id: str
    transition_kind: str
    transition_lineage: CalculationLineage

    def __post_init__(self) -> None:
        if not self.trigger_transaction_id.strip():
            raise ValueError("Cost-basis state trigger transaction ID must not be blank")
        if not self.transition_kind.strip():
            raise ValueError("Cost-basis state transition kind must not be blank")

    def lineage_payload(self) -> dict[str, object]:
        """Return canonical transition input for a durable lineage receipt."""

        return {
            "transition_lineage": self.transition_lineage.lineage_payload(),
            "transition_kind": self.transition_kind,
            "trigger_transaction_id": self.trigger_transaction_id,
        }


def build_cost_basis_state_lineage(
    *,
    algorithm_id: str,
    input_payload: Mapping[str, object],
    output_payload: Mapping[str, object],
) -> CalculationLineage:
    """Bind one final FIFO or AVCO state output to the governed numeric policy."""

    return build_calculation_lineage(
        algorithm_id=algorithm_id,
        algorithm_version=1,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=input_payload,
        output_payload=canonical_cost_basis_output_payload(output_payload),
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    )
