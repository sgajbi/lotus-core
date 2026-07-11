"""Framework-independent generic simulation application workflow."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from portfolio_common.decimal_amounts import decimal_or_none
from portfolio_common.runtime_providers import Clock, IdGenerator

from ..domain.simulation import SimulationChange, SimulationPositionBaseline, SimulationSession
from ..domain.simulation_effects import transaction_quantity_effect
from ..ports.simulation import SimulationBaselineReader, SimulationStore, SimulationUnitOfWork


@dataclass(frozen=True, slots=True)
class CreateSimulationSessionCommand:
    """Create one bounded generic simulation session."""

    portfolio_id: str
    created_by: str | None
    ttl_hours: int


@dataclass(frozen=True, slots=True)
class SimulationChangeCommand:
    """Propose one transaction-shaped change within a session."""

    security_id: str
    transaction_type: str
    quantity: Decimal | None
    price: Decimal | None
    amount: Decimal | None
    currency: str | None
    effective_date: date | None
    metadata: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class SimulationSessionResult:
    """Application result containing current session state."""

    session: SimulationSession


@dataclass(frozen=True, slots=True)
class SimulationChangesResult:
    """Application result containing current versioned change state."""

    session_id: str
    version: int
    changes: list[SimulationChange]


@dataclass(frozen=True, slots=True)
class ProjectedPosition:
    """Position quantity projected from baseline plus proposed changes."""

    security_id: str
    instrument_name: str
    asset_class: str | None
    baseline_quantity: Decimal
    proposed_quantity: Decimal
    delta_quantity: Decimal
    cost_basis: Decimal | None
    cost_basis_local: Decimal | None


@dataclass(frozen=True, slots=True)
class ProjectedPositionsResult:
    """Application result containing the projected position set."""

    session_id: str
    portfolio_id: str
    baseline_as_of: date | None
    positions: list[ProjectedPosition]


@dataclass(frozen=True, slots=True)
class ProjectedSummaryResult:
    """Application result summarizing a projected position set."""

    session_id: str
    portfolio_id: str
    total_baseline_positions: int
    total_proposed_positions: int
    net_delta_quantity: Decimal


@dataclass(slots=True)
class _ProjectionState:
    security_id: str
    baseline_quantity: Decimal
    proposed_quantity: Decimal
    cost_basis: Decimal | None
    cost_basis_local: Decimal | None
    instrument_name: str
    asset_class: str | None


class SimulationServiceError(ValueError):
    """Base error mapped by the simulation delivery adapter."""


class SimulationPortfolioNotFoundError(SimulationServiceError):
    """Raised when a session portfolio does not exist."""


class SimulationSessionNotFoundError(SimulationServiceError):
    """Raised when a simulation session does not exist."""


class SimulationChangeNotFoundError(SimulationServiceError):
    """Raised when a requested simulation change does not exist."""


class SimulationMutationInvalidError(SimulationServiceError):
    """Raised when session lifecycle state rejects a mutation."""


class SimulationService:
    """Coordinate generic simulation state and quantity projection through ports."""

    def __init__(
        self,
        *,
        store: SimulationStore,
        baseline_reader: SimulationBaselineReader,
        unit_of_work: SimulationUnitOfWork,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._store = store
        self._baseline_reader = baseline_reader
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._id_generator = id_generator

    async def create_session(
        self, command: CreateSimulationSessionCommand
    ) -> SimulationSessionResult:
        if not await self._baseline_reader.portfolio_exists(command.portfolio_id):
            raise SimulationPortfolioNotFoundError(
                f"Portfolio with id {command.portfolio_id} not found"
            )
        now = self._clock.utc_now()
        session_id = self._id_generator.new_id()
        await self._store.stage_session(
            session_id=session_id,
            portfolio_id=command.portfolio_id,
            created_by=command.created_by,
            created_at=now,
            expires_at=now + timedelta(hours=command.ttl_hours),
        )
        await self._commit()
        return SimulationSessionResult(session=await self._require_session(session_id))

    async def get_session(self, session_id: str) -> SimulationSessionResult:
        return SimulationSessionResult(session=await self._require_session(session_id))

    async def close_session(self, session_id: str) -> SimulationSessionResult:
        session = await self._require_session(session_id)
        await self._store.stage_session_close(session_id, version=session.version + 1)
        await self._commit()
        return SimulationSessionResult(session=await self._require_session(session_id))

    async def add_changes(
        self,
        session_id: str,
        changes: list[SimulationChangeCommand],
    ) -> SimulationChangesResult:
        session = await self._require_active_session(session_id)
        await self._store.stage_changes(
            session,
            version=session.version + 1,
            changes=[self._change_payload_with_id(item) for item in changes],
        )
        await self._commit()
        return await self._changes_result(session_id)

    async def delete_change(self, session_id: str, change_id: str) -> SimulationChangesResult:
        session = await self._require_active_session(session_id)
        deleted = await self._store.stage_change_delete(
            session_id,
            change_id,
            version=session.version + 1,
        )
        if not deleted:
            await self._unit_of_work.rollback()
            raise SimulationChangeNotFoundError(f"Simulation change {change_id} not found")
        await self._commit()
        return await self._changes_result(session_id)

    async def get_projected_positions(self, session_id: str) -> ProjectedPositionsResult:
        session = await self._require_session(session_id)
        baselines = await self._baseline_reader.get_current_positions(session.portfolio_id)
        states = self._projection_states(baselines)
        changes = await self._store.get_changes(session_id)
        normalized_changes = self._normalized_changes(changes)
        for security_id, _change in normalized_changes:
            states.setdefault(security_id, self._empty_projection_state(security_id))
        await self._enrich_projection_states(states)
        self._apply_changes(states, normalized_changes)
        return ProjectedPositionsResult(
            session_id=session.session_id,
            portfolio_id=session.portfolio_id,
            baseline_as_of=max((row.position_date for row in baselines), default=None),
            positions=self._projected_positions(states),
        )

    async def get_projected_summary(self, session_id: str) -> ProjectedSummaryResult:
        projected = await self.get_projected_positions(session_id)
        return ProjectedSummaryResult(
            session_id=projected.session_id,
            portfolio_id=projected.portfolio_id,
            total_baseline_positions=sum(
                1 for item in projected.positions if item.baseline_quantity > 0
            ),
            total_proposed_positions=len(projected.positions),
            net_delta_quantity=sum(
                (item.delta_quantity for item in projected.positions),
                start=Decimal(0),
            ),
        )

    async def _require_session(self, session_id: str) -> SimulationSession:
        session = await self._store.get_session(session_id)
        if session is None:
            raise SimulationSessionNotFoundError(f"Simulation session {session_id} not found")
        return session

    async def _require_active_session(self, session_id: str) -> SimulationSession:
        session = await self._require_session(session_id)
        if session.status != "ACTIVE":
            raise SimulationMutationInvalidError(f"Simulation session {session_id} is not active")
        if session.expires_at < self._clock.utc_now():
            raise SimulationMutationInvalidError(f"Simulation session {session_id} is expired")
        return session

    async def _commit(self) -> None:
        try:
            await self._unit_of_work.commit()
        except Exception:
            await self._unit_of_work.rollback()
            raise

    async def _changes_result(self, session_id: str) -> SimulationChangesResult:
        session = await self._require_session(session_id)
        return SimulationChangesResult(
            session_id=session.session_id,
            version=session.version,
            changes=await self._store.get_changes(session_id),
        )

    def _change_payload_with_id(self, change: SimulationChangeCommand) -> dict[str, Any]:
        return {
            "change_id": self._id_generator.new_id(),
            "security_id": change.security_id,
            "transaction_type": change.transaction_type,
            "quantity": change.quantity,
            "price": change.price,
            "amount": change.amount,
            "currency": change.currency,
            "effective_date": change.effective_date,
            "metadata": change.metadata,
        }

    @staticmethod
    def _projection_states(
        baselines: list[SimulationPositionBaseline],
    ) -> dict[str, _ProjectionState]:
        return {
            row.security_id: _ProjectionState(
                security_id=row.security_id,
                baseline_quantity=row.quantity,
                proposed_quantity=row.quantity,
                cost_basis=row.cost_basis,
                cost_basis_local=row.cost_basis_local,
                instrument_name=row.instrument_name,
                asset_class=row.asset_class,
            )
            for row in baselines
            if row.security_id
        }

    @staticmethod
    def _normalized_changes(
        changes: list[SimulationChange],
    ) -> list[tuple[str, SimulationChange]]:
        normalized: list[tuple[str, SimulationChange]] = []
        for change in changes:
            security_id = change.security_id.strip()
            if not security_id:
                raise SimulationMutationInvalidError("Simulation change is missing security_id")
            normalized.append((security_id, change))
        return normalized

    @staticmethod
    def _empty_projection_state(security_id: str) -> _ProjectionState:
        return _ProjectionState(
            security_id=security_id,
            baseline_quantity=Decimal(0),
            proposed_quantity=Decimal(0),
            cost_basis=Decimal(0),
            cost_basis_local=Decimal(0),
            instrument_name=security_id,
            asset_class=None,
        )

    async def _enrich_projection_states(self, states: dict[str, _ProjectionState]) -> None:
        instruments = await self._baseline_reader.get_instruments(list(states))
        instrument_map = {row.security_id.strip(): row for row in instruments}
        for security_id, state in states.items():
            instrument = instrument_map.get(security_id)
            if instrument is not None:
                state.instrument_name = instrument.name
                state.asset_class = instrument.asset_class

    @staticmethod
    def _apply_changes(
        states: dict[str, _ProjectionState],
        changes: list[tuple[str, SimulationChange]],
    ) -> None:
        for security_id, change in changes:
            states[security_id].proposed_quantity += transaction_quantity_effect(
                transaction_type=change.transaction_type,
                quantity=change.quantity,
                amount=change.amount,
            )

    @staticmethod
    def _projected_positions(
        states: dict[str, _ProjectionState],
    ) -> list[ProjectedPosition]:
        positions = [
            ProjectedPosition(
                security_id=row.security_id,
                instrument_name=row.instrument_name,
                asset_class=row.asset_class,
                baseline_quantity=row.baseline_quantity,
                proposed_quantity=row.proposed_quantity,
                delta_quantity=row.proposed_quantity - row.baseline_quantity,
                cost_basis=decimal_or_none(row.cost_basis),
                cost_basis_local=decimal_or_none(row.cost_basis_local),
            )
            for row in states.values()
            if row.proposed_quantity > 0
        ]
        positions.sort(key=lambda item: item.security_id)
        return positions
