# src/services/query_service/app/services/simulation_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
from ..repositories.instrument_repository import InstrumentRepository
from ..repositories.position_repository import PositionRepository
from ..repositories.simulation_repository import SimulationRepository

_POSITION_INCREASE_TYPES = {"BUY", "TRANSFER_IN"}
_POSITION_DECREASE_TYPES = {"SELL", "TRANSFER_OUT"}


class SimulationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SimulationRepository(db)
        self.position_repo = PositionRepository(db)
        self.instrument_repo = InstrumentRepository(db)

    async def create_session(
        self, request: SimulationSessionCreateRequest
    ) -> SimulationSessionResponse:
        session = await self.repo.create_session(
            portfolio_id=request.portfolio_id,
            created_by=request.created_by,
            ttl_hours=request.ttl_hours,
        )
        return SimulationSessionResponse(session=session)

    async def get_session(self, session_id: str) -> SimulationSessionResponse:
        session = await self.repo.get_session(session_id)
        if session is None:
            raise ValueError(f"Simulation session {session_id} not found")
        return SimulationSessionResponse(session=session)

    async def close_session(self, session_id: str) -> SimulationSessionResponse:
        session = await self.repo.get_session(session_id)
        if session is None:
            raise ValueError(f"Simulation session {session_id} not found")
        session = await self.repo.close_session(session)
        return SimulationSessionResponse(session=session)

    async def add_changes(
        self, session_id: str, changes: list[dict[str, Any]]
    ) -> SimulationChangesResponse:
        session = await self.repo.get_session(session_id)
        self._validate_session_active(session_id, session)

        session, rows = await self.repo.add_changes(session, changes)
        return SimulationChangesResponse(
            session_id=session.session_id,
            version=session.version,
            changes=[self._to_change_record(row) for row in rows],
        )

    async def delete_change(self, session_id: str, change_id: str) -> SimulationChangesResponse:
        session = await self.repo.get_session(session_id)
        self._validate_session_active(session_id, session)

        deleted = await self.repo.delete_change(session, change_id)
        if not deleted:
            raise ValueError(f"Simulation change {change_id} not found")

        rows = await self.repo.get_changes(session_id)
        return SimulationChangesResponse(
            session_id=session.session_id,
            version=session.version,
            changes=[self._to_change_record(row) for row in rows],
        )

    async def get_projected_positions(self, session_id: str) -> ProjectedPositionsResponse:
        session = await self.repo.get_session(session_id)
        if session is None:
            raise ValueError(f"Simulation session {session_id} not found")

        baseline_results = await self.position_repo.get_latest_positions_by_portfolio(
            session.portfolio_id
        )
        use_snapshot = True
        if not baseline_results:
            baseline_results = await self.position_repo.get_latest_position_history_by_portfolio(
                session.portfolio_id
            )
            use_snapshot = False

        baseline_map: dict[str, dict[str, Any]] = {}
        baseline_as_of = None

        for row, instrument, _state in baseline_results:
            position_date = row.date if use_snapshot else row.position_date
            if baseline_as_of is None or position_date > baseline_as_of:
                baseline_as_of = position_date
            baseline_map[row.security_id] = {
                "security_id": row.security_id,
                "baseline_quantity": float(row.quantity),
                "proposed_quantity": float(row.quantity),
                "cost_basis": float(row.cost_basis) if row.cost_basis is not None else None,
                "cost_basis_local": float(row.cost_basis_local)
                if row.cost_basis_local is not None
                else None,
                "instrument_name": instrument.name if instrument else row.security_id,
                "asset_class": instrument.asset_class if instrument else None,
            }

        changes = await self.repo.get_changes(session_id)
        security_ids = {item.security_id for item in changes}
        for security_id in security_ids:
            if security_id not in baseline_map:
                baseline_map[security_id] = {
                    "security_id": security_id,
                    "baseline_quantity": 0.0,
                    "proposed_quantity": 0.0,
                    "cost_basis": 0.0,
                    "cost_basis_local": 0.0,
                    "instrument_name": security_id,
                    "asset_class": None,
                }

        instruments = await self.instrument_repo.get_by_security_ids(list(baseline_map.keys()))
        instrument_map = {item.security_id: item for item in instruments}

        for security_id, record in baseline_map.items():
            instrument = instrument_map.get(security_id)
            if instrument is not None:
                record["instrument_name"] = instrument.name
                record["asset_class"] = instrument.asset_class

        for change in changes:
            record = baseline_map[change.security_id]
            qty = self._change_quantity_effect(change)
            record["proposed_quantity"] += qty

        response_rows: list[ProjectedPositionRecord] = []
        for row in baseline_map.values():
            if row["proposed_quantity"] <= 0:
                continue
            response_rows.append(
                ProjectedPositionRecord(
                    security_id=row["security_id"],
                    instrument_name=row["instrument_name"],
                    asset_class=row["asset_class"],
                    baseline_quantity=row["baseline_quantity"],
                    proposed_quantity=row["proposed_quantity"],
                    delta_quantity=row["proposed_quantity"] - row["baseline_quantity"],
                    cost_basis=row["cost_basis"],
                    cost_basis_local=row["cost_basis_local"],
                )
            )

        response_rows.sort(key=lambda item: item.security_id)
        return ProjectedPositionsResponse(
            session_id=session.session_id,
            portfolio_id=session.portfolio_id,
            baseline_as_of=baseline_as_of,
            positions=response_rows,
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
    def _change_quantity_effect(change) -> float:
        txn_type = str(change.transaction_type).upper()
        magnitude = float(change.quantity or 0.0)
        if txn_type in _POSITION_INCREASE_TYPES:
            return magnitude
        if txn_type in _POSITION_DECREASE_TYPES:
            return -magnitude
        return 0.0

    @staticmethod
    def _validate_session_active(session_id: str, session) -> None:
        if session is None:
            raise ValueError(f"Simulation session {session_id} not found")
        if session.status != "ACTIVE":
            raise ValueError(f"Simulation session {session_id} is not active")
        if session.expires_at is not None and session.expires_at < datetime.now(timezone.utc):
            raise ValueError(f"Simulation session {session_id} is expired")

    @staticmethod
    def _to_change_record(row) -> SimulationChangeRecord:
        return SimulationChangeRecord(
            change_id=row.change_id,
            session_id=row.session_id,
            portfolio_id=row.portfolio_id,
            security_id=row.security_id,
            transaction_type=row.transaction_type,
            quantity=(float(row.quantity) if row.quantity is not None else None),
            price=(float(row.price) if row.price is not None else None),
            amount=(float(row.amount) if row.amount is not None else None),
            currency=row.currency,
            effective_date=row.effective_date,
            metadata=row.change_metadata,
            created_at=row.created_at,
        )
