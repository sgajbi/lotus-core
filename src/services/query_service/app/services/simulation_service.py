# src/services/query_service/app/services/simulation_service.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
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
from .position_flow_effects import transaction_quantity_effect_decimal


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
                "baseline_quantity": Decimal(str(row.quantity)),
                "proposed_quantity": Decimal(str(row.quantity)),
                "cost_basis": Decimal(str(row.cost_basis)) if row.cost_basis is not None else None,
                "cost_basis_local": Decimal(str(row.cost_basis_local))
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
                    "baseline_quantity": Decimal("0"),
                    "proposed_quantity": Decimal("0"),
                    "cost_basis": Decimal("0"),
                    "cost_basis_local": Decimal("0"),
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
    def _change_quantity_effect(change):
        return transaction_quantity_effect_decimal(
            transaction_type=getattr(change, "transaction_type", None),
            quantity=getattr(change, "quantity", None),
        )

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
            quantity=(Decimal(str(row.quantity)) if row.quantity is not None else None),
            price=(Decimal(str(row.price)) if row.price is not None else None),
            amount=(Decimal(str(row.amount)) if row.amount is not None else None),
            currency=row.currency,
            effective_date=row.effective_date,
            metadata=row.change_metadata,
            created_at=row.created_at,
        )
