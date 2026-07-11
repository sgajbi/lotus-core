"""Ports required by the generic simulation application workflow."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from ..domain.simulation import (
    SimulationChange,
    SimulationInstrument,
    SimulationPositionBaseline,
    SimulationSession,
)


class SimulationStore(Protocol):
    """Persist generic simulation session and change state."""

    async def stage_session(
        self,
        *,
        session_id: str,
        portfolio_id: str,
        created_by: str | None,
        created_at: datetime,
        expires_at: datetime,
    ) -> None: ...

    async def get_session(self, session_id: str) -> SimulationSession | None: ...

    async def stage_session_close(self, session_id: str, *, version: int) -> None: ...

    async def stage_changes(
        self,
        session: SimulationSession,
        *,
        version: int,
        changes: Sequence[dict[str, Any]],
    ) -> None: ...

    async def stage_change_delete(
        self,
        session_id: str,
        change_id: str,
        *,
        version: int,
    ) -> bool: ...

    async def get_changes(self, session_id: str) -> list[SimulationChange]: ...


class SimulationBaselineReader(Protocol):
    """Read immutable portfolio baseline and instrument inputs."""

    async def portfolio_exists(self, portfolio_id: str) -> bool: ...

    async def get_current_positions(
        self, portfolio_id: str
    ) -> list[SimulationPositionBaseline]: ...

    async def get_instruments(self, security_ids: list[str]) -> list[SimulationInstrument]: ...


class SimulationUnitOfWork(Protocol):
    """Commit or roll back one simulation mutation."""

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
