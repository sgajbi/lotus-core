# src/services/query_service/app/repositories/simulation_repository.py
from __future__ import annotations

from datetime import datetime
from typing import cast

from portfolio_common.database_models import SimulationChange, SimulationSession
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.decimal_amounts import decimal_or_none


class SimulationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(
        self,
        *,
        session_id: str,
        portfolio_id: str,
        created_by: str | None,
        created_at: datetime,
        expires_at: datetime,
    ) -> SimulationSession:
        session = SimulationSession(
            session_id=session_id,
            portfolio_id=portfolio_id,
            status="ACTIVE",
            version=1,
            created_by=created_by,
            created_at=created_at,
            expires_at=expires_at,
        )
        self.db.add(session)
        return session

    async def get_session(self, session_id: str) -> SimulationSession | None:
        stmt = select(SimulationSession).where(SimulationSession.session_id == session_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def close_session(self, session: SimulationSession) -> SimulationSession:
        session.status = "CLOSED"
        return session

    async def add_changes(
        self,
        session: SimulationSession,
        changes: list[dict],
    ) -> tuple[SimulationSession, list[SimulationChange]]:
        rows: list[SimulationChange] = []
        for item in changes:
            row = SimulationChange(
                change_id=item["change_id"],
                session_id=session.session_id,
                portfolio_id=session.portfolio_id,
                security_id=item["security_id"],
                transaction_type=item["transaction_type"],
                quantity=decimal_or_none(item.get("quantity")),
                price=decimal_or_none(item.get("price")),
                amount=decimal_or_none(item.get("amount")),
                currency=item.get("currency"),
                effective_date=item.get("effective_date"),
                change_metadata=item.get("metadata"),
            )
            self.db.add(row)
            rows.append(row)

        return session, rows

    async def delete_change(self, session: SimulationSession, change_id: str) -> bool:
        stmt = delete(SimulationChange).where(
            SimulationChange.session_id == session.session_id,
            SimulationChange.change_id == change_id,
        )
        result = await self.db.execute(stmt)
        if (result.rowcount or 0) == 0:
            return False

        return True

    async def get_changes(self, session_id: str) -> list[SimulationChange]:
        stmt = (
            select(SimulationChange)
            .where(SimulationChange.session_id == session_id)
            .order_by(SimulationChange.created_at.asc(), SimulationChange.id.asc())
        )
        result = await self.db.execute(stmt)
        return cast(list[SimulationChange], result.scalars().all())
