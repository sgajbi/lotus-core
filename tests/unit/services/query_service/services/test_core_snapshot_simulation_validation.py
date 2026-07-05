from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.dtos.core_snapshot_dto import (
    CoreSnapshotMode,
    CoreSnapshotRequest,
    CoreSnapshotSection,
)
from src.services.query_service.app.services.core_snapshot_errors import (
    CoreSnapshotBadRequestError,
    CoreSnapshotConflictError,
    CoreSnapshotNotFoundError,
)
from src.services.query_service.app.services.core_snapshot_simulation_validation import (
    CoreSnapshotSimulationSessionValidator,
)

pytestmark = pytest.mark.asyncio


async def test_simulation_session_validator_returns_matching_session() -> None:
    simulation_repo = AsyncMock()
    session = SimpleNamespace(
        session_id="SIM_1",
        portfolio_id="PORT_001",
        version=3,
    )
    simulation_repo.get_session.return_value = session
    validator = CoreSnapshotSimulationSessionValidator(simulation_repo=simulation_repo)

    result = await validator.validated_session(
        portfolio_id="PORT_001",
        request=CoreSnapshotRequest(
            as_of_date="2026-02-27",
            snapshot_mode=CoreSnapshotMode.SIMULATION,
            sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
            simulation={"session_id": "SIM_1", "expected_version": 3},
        ),
    )

    assert result is session
    simulation_repo.get_session.assert_awaited_once_with("SIM_1")


async def test_simulation_session_validator_requires_simulation_options() -> None:
    validator = CoreSnapshotSimulationSessionValidator(simulation_repo=AsyncMock())

    with pytest.raises(
        CoreSnapshotBadRequestError,
        match="simulation options are required",
    ):
        await validator.validated_session(
            portfolio_id="PORT_001",
            request=SimpleNamespace(simulation=None),
        )


async def test_simulation_session_validator_requires_existing_session() -> None:
    simulation_repo = AsyncMock()
    simulation_repo.get_session.return_value = None
    validator = CoreSnapshotSimulationSessionValidator(simulation_repo=simulation_repo)

    with pytest.raises(CoreSnapshotNotFoundError, match="Simulation session SIM_1 not found"):
        await validator.validated_session(
            portfolio_id="PORT_001",
            request=CoreSnapshotRequest(
                as_of_date="2026-02-27",
                snapshot_mode=CoreSnapshotMode.SIMULATION,
                sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
                simulation={"session_id": "SIM_1"},
            ),
        )


async def test_simulation_session_validator_rejects_portfolio_mismatch() -> None:
    simulation_repo = AsyncMock()
    simulation_repo.get_session.return_value = SimpleNamespace(
        session_id="SIM_1",
        portfolio_id="OTHER_PORT",
        version=3,
    )
    validator = CoreSnapshotSimulationSessionValidator(simulation_repo=simulation_repo)

    with pytest.raises(
        CoreSnapshotConflictError,
        match="does not belong to requested portfolio",
    ):
        await validator.validated_session(
            portfolio_id="PORT_001",
            request=CoreSnapshotRequest(
                as_of_date="2026-02-27",
                snapshot_mode=CoreSnapshotMode.SIMULATION,
                sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
                simulation={"session_id": "SIM_1"},
            ),
        )


async def test_simulation_session_validator_rejects_expected_version_mismatch() -> None:
    simulation_repo = AsyncMock()
    simulation_repo.get_session.return_value = SimpleNamespace(
        session_id="SIM_1",
        portfolio_id="PORT_001",
        version=3,
    )
    validator = CoreSnapshotSimulationSessionValidator(simulation_repo=simulation_repo)

    with pytest.raises(CoreSnapshotConflictError, match="expected_version mismatch"):
        await validator.validated_session(
            portfolio_id="PORT_001",
            request=CoreSnapshotRequest(
                as_of_date="2026-02-27",
                snapshot_mode=CoreSnapshotMode.SIMULATION,
                sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
                simulation={"session_id": "SIM_1", "expected_version": 99},
            ),
        )


async def test_simulation_session_validator_rejects_projected_sections_in_baseline_mode() -> None:
    with pytest.raises(
        CoreSnapshotBadRequestError,
        match="Projected and delta sections require snapshot_mode=SIMULATION",
    ):
        CoreSnapshotSimulationSessionValidator.validate_baseline_snapshot_sections(
            [CoreSnapshotSection.POSITIONS_DELTA]
        )
