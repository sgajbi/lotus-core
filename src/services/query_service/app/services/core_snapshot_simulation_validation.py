from __future__ import annotations

from typing import Any

from ..dtos.core_snapshot_dto import CoreSnapshotRequest, CoreSnapshotSection
from .core_snapshot_errors import (
    CoreSnapshotBadRequestError,
    CoreSnapshotConflictError,
    CoreSnapshotNotFoundError,
)


class CoreSnapshotSimulationSessionValidator:
    def __init__(self, *, simulation_repo: Any) -> None:
        self._simulation_repo = simulation_repo

    async def validated_session(
        self,
        *,
        portfolio_id: str,
        request: CoreSnapshotRequest,
    ) -> Any:
        session_opts = self._required_simulation_options(request)
        session = await self._required_simulation_session(session_opts.session_id)
        self._validate_simulation_portfolio(session=session, portfolio_id=portfolio_id)
        self._validate_simulation_version(
            session=session,
            expected_version=session_opts.expected_version,
        )
        return session

    @staticmethod
    def _required_simulation_options(request: CoreSnapshotRequest) -> Any:
        session_opts = request.simulation
        if session_opts is None:
            raise CoreSnapshotBadRequestError(
                "simulation options are required when snapshot_mode=SIMULATION"
            )
        return session_opts

    async def _required_simulation_session(self, session_id: str) -> Any:
        session = await self._simulation_repo.get_session(session_id)
        if session is None:
            raise CoreSnapshotNotFoundError(f"Simulation session {session_id} not found")
        return session

    @staticmethod
    def _validate_simulation_portfolio(*, session: Any, portfolio_id: str) -> None:
        if session.portfolio_id != portfolio_id:
            raise CoreSnapshotConflictError(
                "Simulation session does not belong to requested portfolio"
            )

    @staticmethod
    def _validate_simulation_version(*, session: Any, expected_version: int | None) -> None:
        if expected_version is not None and session.version != expected_version:
            raise CoreSnapshotConflictError("Simulation expected_version mismatch")

    @staticmethod
    def validate_baseline_snapshot_sections(sections: list[CoreSnapshotSection]) -> None:
        if (
            CoreSnapshotSection.POSITIONS_PROJECTED in sections
            or CoreSnapshotSection.POSITIONS_DELTA in sections
        ):
            raise CoreSnapshotBadRequestError(
                "Projected and delta sections require snapshot_mode=SIMULATION"
            )
