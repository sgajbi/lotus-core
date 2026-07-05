# src/services/query_service/app/services/simulation_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from portfolio_common.runtime_providers import Clock, IdGenerator, SystemClock, UuidIdGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.simulation_dto import (
    ProjectedPositionRecord,
    ProjectedPositionsResponse,
    ProjectedSummaryResponse,
    SimulationChangeRecord,
    SimulationChangesResponse,
    SimulationSessionCreateRequest,
    SimulationSessionResponse,
)
from ..infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from ..ports.unit_of_work import UnitOfWork
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.instrument_repository import InstrumentRepository
from ..repositories.position_repository import PositionRepository
from ..repositories.simulation_repository import SimulationRepository
from .decimal_amounts import decimal_or_none, decimal_or_zero
from .position_flow_effects import transaction_quantity_effect_decimal


@dataclass(frozen=True)
class _ProjectedBaseline:
    records: dict[str, dict[str, Any]]
    as_of_date: Any | None


@dataclass(frozen=True)
class _NormalizedSimulationChange:
    security_id: str
    change: Any


class SimulationServiceError(ValueError):
    """Base class for simulation service errors mapped by control-plane routers."""


class SimulationPortfolioNotFoundError(SimulationServiceError):
    pass


class SimulationSessionNotFoundError(SimulationServiceError):
    pass


class SimulationChangeNotFoundError(SimulationServiceError):
    pass


class SimulationMutationInvalidError(SimulationServiceError):
    pass


class SimulationService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
        unit_of_work: UnitOfWork | None = None,
    ):
        self.db = db
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or UuidIdGenerator()
        self._unit_of_work = unit_of_work or SqlAlchemyUnitOfWork(db)
        self.repo = SimulationRepository(db)
        self.position_repo = PositionRepository(db)
        self.instrument_repo = InstrumentRepository(db)

    async def create_session(
        self, request: SimulationSessionCreateRequest
    ) -> SimulationSessionResponse:
        await self._ensure_portfolio_exists(request.portfolio_id)
        now = self._clock.utc_now()
        session = await self.repo.create_session(
            session_id=self._id_generator.new_id(),
            portfolio_id=request.portfolio_id,
            created_by=request.created_by,
            created_at=now,
            expires_at=now + timedelta(hours=request.ttl_hours),
        )
        await self._commit_and_refresh(session)
        return SimulationSessionResponse(session=session)

    async def get_session(self, session_id: str) -> SimulationSessionResponse:
        session = await self.repo.get_session(session_id)
        if session is None:
            raise SimulationSessionNotFoundError(f"Simulation session {session_id} not found")
        return SimulationSessionResponse(session=session)

    async def close_session(self, session_id: str) -> SimulationSessionResponse:
        session = await self.repo.get_session(session_id)
        if session is None:
            raise SimulationSessionNotFoundError(f"Simulation session {session_id} not found")
        session.version += 1
        session = await self.repo.close_session(session)
        await self._commit_and_refresh(session)
        return SimulationSessionResponse(session=session)

    async def add_changes(
        self, session_id: str, changes: list[dict[str, Any]]
    ) -> SimulationChangesResponse:
        session = self._require_active_session(
            session_id,
            await self.repo.get_session(session_id),
        )

        session.version += 1
        session, rows = await self.repo.add_changes(
            session,
            [self._change_payload_with_id(item) for item in changes],
        )
        await self._commit_and_refresh(session, *rows)
        return SimulationChangesResponse(
            session_id=session.session_id,
            version=session.version,
            changes=[self._to_change_record(row) for row in rows],
        )

    async def delete_change(self, session_id: str, change_id: str) -> SimulationChangesResponse:
        session = self._require_active_session(
            session_id,
            await self.repo.get_session(session_id),
        )

        deleted = await self.repo.delete_change(session, change_id)
        if not deleted:
            await self._unit_of_work.rollback()
            raise SimulationChangeNotFoundError(f"Simulation change {change_id} not found")

        session.version += 1
        await self._commit_and_refresh(session)
        rows = await self.repo.get_changes(session_id)
        return SimulationChangesResponse(
            session_id=session.session_id,
            version=session.version,
            changes=[self._to_change_record(row) for row in rows],
        )

    async def get_projected_positions(self, session_id: str) -> ProjectedPositionsResponse:
        session = await self.repo.get_session(session_id)
        if session is None:
            raise SimulationSessionNotFoundError(f"Simulation session {session_id} not found")

        baseline = await self._projected_baseline(session.portfolio_id)
        changes = await self.repo.get_changes(session_id)
        baseline_map = baseline.records
        normalized_changes = self._normalized_simulation_changes(changes)

        self._ensure_projection_records_for_changes(baseline_map, normalized_changes)
        await self._enrich_projection_records_with_instruments(baseline_map)
        self._apply_projection_changes(baseline_map, normalized_changes)

        return ProjectedPositionsResponse(
            session_id=session.session_id,
            portfolio_id=session.portfolio_id,
            baseline_as_of=baseline.as_of_date,
            positions=self._projected_position_records(baseline_map),
        )

    async def get_projected_summary(self, session_id: str) -> ProjectedSummaryResponse:
        projected = await self.get_projected_positions(session_id)
        net_delta = sum(item.delta_quantity for item in projected.positions)
        baseline_count = sum(1 for item in projected.positions if item.baseline_quantity > 0)

        return ProjectedSummaryResponse(
            session_id=projected.session_id,
            portfolio_id=projected.portfolio_id,
            total_baseline_positions=baseline_count,
            total_proposed_positions=len(projected.positions),
            net_delta_quantity=net_delta,
        )

    @staticmethod
    def _change_quantity_effect(change):
        return transaction_quantity_effect_decimal(
            transaction_type=getattr(change, "transaction_type", None),
            quantity=getattr(change, "quantity", None),
            amount=getattr(change, "amount", None),
        )

    def _validate_session_active(self, session_id: str, session) -> None:
        if session is None:
            raise SimulationSessionNotFoundError(f"Simulation session {session_id} not found")
        if session.status != "ACTIVE":
            raise SimulationMutationInvalidError(f"Simulation session {session_id} is not active")
        if session.expires_at is not None and session.expires_at < self._clock.utc_now():
            raise SimulationMutationInvalidError(f"Simulation session {session_id} is expired")

    def _require_active_session(self, session_id: str, session):
        self._validate_session_active(session_id, session)
        return session

    def _change_payload_with_id(self, item: dict[str, Any]) -> dict[str, Any]:
        return {**item, "change_id": self._id_generator.new_id()}

    async def _commit_and_refresh(self, *entities: Any) -> None:
        try:
            await self._unit_of_work.commit()
        except Exception:
            await self._unit_of_work.rollback()
            raise
        for entity in entities:
            await self._unit_of_work.refresh(entity)

    async def _projected_baseline(self, portfolio_id: str) -> _ProjectedBaseline:
        baseline_results = await self.position_repo.get_latest_positions_by_portfolio(portfolio_id)
        use_snapshot = True
        if not baseline_results:
            baseline_results = await self.position_repo.get_latest_position_history_by_portfolio(
                portfolio_id
            )
            use_snapshot = False

        baseline_map: dict[str, dict[str, Any]] = {}
        baseline_as_of = None
        for row, instrument, _state in baseline_results:
            position_date = row.date if use_snapshot else row.position_date
            baseline_as_of = self._latest_baseline_as_of(baseline_as_of, position_date)
            security_id = normalize_security_id(row.security_id)
            if not security_id:
                continue
            baseline_map[security_id] = self._baseline_projection_record(
                row=row,
                instrument=instrument,
                security_id=security_id,
            )
        return _ProjectedBaseline(records=baseline_map, as_of_date=baseline_as_of)

    @staticmethod
    def _latest_baseline_as_of(current_as_of, position_date):
        if current_as_of is None or position_date > current_as_of:
            return position_date
        return current_as_of

    @staticmethod
    def _baseline_projection_record(*, row, instrument, security_id: str) -> dict[str, Any]:
        baseline_quantity = decimal_or_zero(row.quantity)
        return {
            "security_id": security_id,
            "baseline_quantity": baseline_quantity,
            "proposed_quantity": baseline_quantity,
            "cost_basis": decimal_or_none(row.cost_basis),
            "cost_basis_local": decimal_or_none(row.cost_basis_local),
            "instrument_name": instrument.name if instrument else security_id,
            "asset_class": instrument.asset_class if instrument else None,
        }

    @staticmethod
    def _normalized_simulation_changes(changes: list[Any]) -> list[_NormalizedSimulationChange]:
        normalized_changes: list[_NormalizedSimulationChange] = []
        for change in changes:
            security_id = normalize_security_id(change.security_id)
            if not security_id:
                raise SimulationMutationInvalidError("Simulation change is missing security_id")
            normalized_changes.append(
                _NormalizedSimulationChange(security_id=security_id, change=change)
            )
        return normalized_changes

    @staticmethod
    def _ensure_projection_records_for_changes(
        baseline_map: dict[str, dict[str, Any]],
        normalized_changes: list[_NormalizedSimulationChange],
    ) -> None:
        for security_id in {item.security_id for item in normalized_changes}:
            if security_id not in baseline_map:
                baseline_map[security_id] = SimulationService._empty_projection_record(security_id)

    @staticmethod
    def _empty_projection_record(security_id: str) -> dict[str, Any]:
        return {
            "security_id": security_id,
            "baseline_quantity": Decimal("0"),
            "proposed_quantity": Decimal("0"),
            "cost_basis": Decimal("0"),
            "cost_basis_local": Decimal("0"),
            "instrument_name": security_id,
            "asset_class": None,
        }

    async def _enrich_projection_records_with_instruments(
        self,
        baseline_map: dict[str, dict[str, Any]],
    ) -> None:
        instruments = await self.instrument_repo.get_by_security_ids(list(baseline_map.keys()))
        instrument_map = self._instrument_map_by_security_id(instruments)
        for security_id, record in baseline_map.items():
            instrument = instrument_map.get(security_id)
            if instrument is not None:
                record["instrument_name"] = instrument.name
                record["asset_class"] = instrument.asset_class

    @staticmethod
    def _instrument_map_by_security_id(instruments: list[Any]) -> dict[str, Any]:
        return {
            security_id: item
            for item in instruments
            if (security_id := normalize_security_id(item.security_id))
        }

    def _apply_projection_changes(
        self,
        baseline_map: dict[str, dict[str, Any]],
        normalized_changes: list[_NormalizedSimulationChange],
    ) -> None:
        for normalized_change in normalized_changes:
            record = baseline_map[normalized_change.security_id]
            record["proposed_quantity"] += self._change_quantity_effect(normalized_change.change)

    @staticmethod
    def _projected_position_records(
        baseline_map: dict[str, dict[str, Any]],
    ) -> list[ProjectedPositionRecord]:
        response_rows = [
            SimulationService._projected_position_record(row)
            for row in baseline_map.values()
            if row["proposed_quantity"] > 0
        ]
        response_rows.sort(key=lambda item: item.security_id)
        return response_rows

    @staticmethod
    def _projected_position_record(row: dict[str, Any]) -> ProjectedPositionRecord:
        return ProjectedPositionRecord(
            security_id=row["security_id"],
            instrument_name=row["instrument_name"],
            asset_class=row["asset_class"],
            baseline_quantity=row["baseline_quantity"],
            proposed_quantity=row["proposed_quantity"],
            delta_quantity=row["proposed_quantity"] - row["baseline_quantity"],
            cost_basis=row["cost_basis"],
            cost_basis_local=row["cost_basis_local"],
        )

    async def _ensure_portfolio_exists(self, portfolio_id: str) -> None:
        if not await self.position_repo.portfolio_exists(portfolio_id):
            raise SimulationPortfolioNotFoundError(f"Portfolio with id {portfolio_id} not found")

    @staticmethod
    def _to_change_record(row) -> SimulationChangeRecord:
        return SimulationChangeRecord(
            change_id=row.change_id,
            session_id=row.session_id,
            portfolio_id=row.portfolio_id,
            security_id=row.security_id,
            transaction_type=row.transaction_type,
            quantity=decimal_or_none(row.quantity),
            price=decimal_or_none(row.price),
            amount=decimal_or_none(row.amount),
            currency=row.currency,
            effective_date=row.effective_date,
            metadata=row.change_metadata,
            created_at=row.created_at,
        )
