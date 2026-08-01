"""Build deterministic lineage at durable cost-basis state boundaries."""

from collections.abc import Mapping

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1


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
        output_payload=output_payload,
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    )
