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
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.instrument_repository import InstrumentRepository
from ..repositories.position_repository import PositionRepository
from ..repositories.simulation_repository import SimulationRepository
from .decimal_amounts import decimal_or_none, decimal_or_zero
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
        await self._ensure_portfolio_exists(request.portfolio_id)
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
            security_id = normalize_security_id(row.security_id)
            if not security_id:
                continue
            baseline_map[security_id] = {
                "security_id": security_id,
                "baseline_quantity": decimal_or_zero(row.quantity),
                "proposed_quantity": decimal_or_zero(row.quantity),
                "cost_basis": decimal_or_none(row.cost_basis),
                "cost_basis_local": decimal_or_none(row.cost_basis_local),
                "instrument_name": instrument.name if instrument else security_id,
                "asset_class": instrument.asset_class if instrument else None,
            }

        changes = await self.repo.get_changes(session_id)
        normalized_changes: list[tuple[str, Any]] = []
        for change in changes:
            security_id = normalize_security_id(change.security_id)
            if not security_id:
                raise ValueError("Simulation change is missing security_id")
            normalized_changes.append((security_id, change))

        security_ids = {security_id for security_id, _change in normalized_changes}
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
        instrument_map = {
            security_id: item
            for item in instruments
            if (security_id := normalize_security_id(item.security_id))
        }

        for security_id, record in baseline_map.items():
            instrument = instrument_map.get(security_id)
            if instrument is not None:
                record["instrument_name"] = instrument.name
                record["asset_class"] = instrument.asset_class

        for security_id, change in normalized_changes:
            record = baseline_map[security_id]
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
            amount=getattr(change, "amount", None),
        )

    @staticmethod
    def _validate_session_active(session_id: str, session) -> None:
        if session is None:
            raise ValueError(f"Simulation session {session_id} not found")
        if session.status != "ACTIVE":
            raise ValueError(f"Simulation session {session_id} is not active")
        if session.expires_at is not None and session.expires_at < datetime.now(timezone.utc):
            raise ValueError(f"Simulation session {session_id} is expired")

    async def _ensure_portfolio_exists(self, portfolio_id: str) -> None:
        if not await self.position_repo.portfolio_exists(portfolio_id):
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

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
