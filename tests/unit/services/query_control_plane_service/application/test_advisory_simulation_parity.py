import pytest

from src.services.query_control_plane_service.app.application.advisory_simulation.service import (
    execute_advisory_simulation as _execute_advisory_simulation,
)
from src.services.query_control_plane_service.app.contracts.advisory_simulation_models import (
    ProposalSimulateRequest,
)
from tests.shared.advisory_simulation_parity import (
    iter_parity_scenarios,
    normalize_result_for_parity,
)


class _FixedIdGenerator:
    def new_id(self) -> str:
        return "00000000-0000-0000-0000-000000000001"

    def new_hex(self) -> str:
        return "00000000000000000000000000000001"


def execute_advisory_simulation(**kwargs: object):
    return _execute_advisory_simulation(
        **kwargs,
        id_generator=_FixedIdGenerator(),
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
