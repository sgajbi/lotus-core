from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import CalculationLineage

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis.state_lineage import (  # noqa: E501
    CostBasisStateTransitionEvidence,
    build_cost_basis_state_lineage,
)


def _transition_lineage() -> CalculationLineage:
    return build_cost_basis_state_lineage(
        algorithm_id="test-cost-basis-transition",
        input_payload={"transaction_id": "SELL01"},
        output_payload={"remaining_quantity": Decimal("5")},
    )


def test_transition_evidence_exposes_complete_lineage_payload() -> None:
    transition_lineage = _transition_lineage()
    evidence = CostBasisStateTransitionEvidence(
        trigger_transaction_id="SELL01",
        transition_kind="selected_lots",
        transition_lineage=transition_lineage,
    )

    assert evidence.lineage_payload() == {
        "transition_lineage": transition_lineage.lineage_payload(),
        "transition_kind": "selected_lots",
        "trigger_transaction_id": "SELL01",
    }


@pytest.mark.parametrize(
    ("trigger_transaction_id", "transition_kind", "expected_message"),
    [
        ("   ", "selected_lots", "trigger transaction ID must not be blank"),
        ("SELL01", "\t", "transition kind must not be blank"),
    ],
)
def test_transition_evidence_rejects_blank_identity_fields(
    trigger_transaction_id: str,
    transition_kind: str,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        CostBasisStateTransitionEvidence(
            trigger_transaction_id=trigger_transaction_id,
            transition_kind=transition_kind,
            transition_lineage=_transition_lineage(),
        )
