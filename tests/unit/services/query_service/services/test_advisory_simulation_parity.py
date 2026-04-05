import pytest

from src.services.query_service.app.advisory_simulation.models import ProposalSimulateRequest
from src.services.query_service.app.services.advisory_simulation_service import (
    execute_advisory_simulation,
)
from tests.shared.advisory_simulation_parity import (
    iter_parity_scenarios,
    normalize_result_for_parity,
)


@pytest.mark.parametrize(
    ("scenario_name", "request_hash", "payload", "expected"),
    [
        (
            scenario["name"],
            scenario["request_hash"],
            scenario["payload"],
            scenario["expected"],
        )
        for scenario in iter_parity_scenarios()
    ],
    ids=[scenario["name"] for scenario in iter_parity_scenarios()],
)
def test_canonical_simulation_service_matches_curated_parity_scenarios(
    scenario_name: str,
    request_hash: str,
    payload: dict,
    expected: dict,
) -> None:
    request = ProposalSimulateRequest.model_validate(payload)

    result = execute_advisory_simulation(
        request=request,
        request_hash=request_hash,
        idempotency_key=None,
        correlation_id="corr-parity",
        simulation_contract_version="advisory-simulation.v1",
    )

    assert normalize_result_for_parity(result) == expected, scenario_name
