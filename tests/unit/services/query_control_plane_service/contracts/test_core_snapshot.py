import pytest
from pydantic import ValidationError

from src.services.query_control_plane_service.app.contracts.core_snapshot import (
    CoreSnapshotMode,
    CoreSnapshotRequest,
    CoreSnapshotSection,
)


def test_core_snapshot_request_accepts_valid_baseline_payload() -> None:
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
    )

    assert request.snapshot_mode == CoreSnapshotMode.BASELINE
    assert request.sections == [CoreSnapshotSection.POSITIONS_BASELINE]


def test_core_snapshot_request_rejects_empty_sections() -> None:
    with pytest.raises(ValidationError, match="sections must contain at least one value"):
        CoreSnapshotRequest(
            as_of_date="2026-02-27",
            snapshot_mode=CoreSnapshotMode.BASELINE,
            sections=[],
        )


def test_core_snapshot_request_requires_simulation_for_simulation_mode() -> None:
    with pytest.raises(
        ValidationError, match="simulation.session_id is required for SIMULATION mode"
    ):
        CoreSnapshotRequest(
            as_of_date="2026-02-27",
            snapshot_mode=CoreSnapshotMode.SIMULATION,
            sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        )


def test_core_snapshot_request_rejects_simulation_block_for_baseline_mode() -> None:
    with pytest.raises(ValidationError, match="simulation block is not allowed for BASELINE mode"):
        CoreSnapshotRequest(
            as_of_date="2026-02-27",
            snapshot_mode=CoreSnapshotMode.BASELINE,
            sections=[CoreSnapshotSection.POSITIONS_BASELINE],
            simulation={"session_id": "SIM_1"},
        )
