"""One-statement SQLAlchemy adapter for lot-to-position parity evidence."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import PositionHistory, PositionLotState, PositionState
from sqlalchemy import and_, func, or_, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cost_basis.lot_position_reconciliation import (
    LOT_QUANTITY_VS_POSITION_MISMATCH,
    LotPositionParityAssessment,
    LotPositionParityKey,
    LotPositionParityStatus,
)


class SqlAlchemyLotPositionParityAdapter:
    """Assess an ordered page without per-key database round trips."""

    def __init__(self, *, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def assess_page(
        self,
        *,
        portfolio_id: str | None,
        after: LotPositionParityKey | None,
        limit: int,
    ) -> tuple[LotPositionParityAssessment, ...]:
        keys_stmt = select(
            PositionState.portfolio_id.label("portfolio_id"),
            PositionState.security_id.label("security_id"),
            PositionState.epoch.label("epoch"),
        ).order_by(PositionState.portfolio_id, PositionState.security_id)
        if portfolio_id is not None:
            keys_stmt = keys_stmt.where(PositionState.portfolio_id == portfolio_id)
        if after is not None:
            keys_stmt = keys_stmt.where(
                or_(
                    PositionState.portfolio_id > after.portfolio_id,
                    and_(
                        PositionState.portfolio_id == after.portfolio_id,
                        PositionState.security_id > after.security_id,
                    ),
                )
            )
        keys = keys_stmt.limit(limit).cte("lot_position_parity_keys")
        lot_quantity = (
            select(func.coalesce(func.sum(PositionLotState.open_quantity), 0))
            .where(
                PositionLotState.portfolio_id == keys.c.portfolio_id,
                PositionLotState.security_id == keys.c.security_id,
            )
            .correlate(keys)
            .scalar_subquery()
        )
        position_quantity = (
            select(PositionHistory.quantity)
            .where(
                PositionHistory.portfolio_id == keys.c.portfolio_id,
                PositionHistory.security_id == keys.c.security_id,
                PositionHistory.epoch == keys.c.epoch,
            )
            .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
            .limit(1)
            .correlate(keys)
            .scalar_subquery()
        )
        stmt = select(
            keys.c.portfolio_id,
            keys.c.security_id,
            keys.c.epoch,
            lot_quantity.label("lot_quantity"),
            position_quantity.label("position_quantity"),
        ).order_by(keys.c.portfolio_id, keys.c.security_id)
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return tuple(_assessment(row) for row in rows)


def _assessment(row: Row[Any]) -> LotPositionParityAssessment:
    lot_quantity = Decimal(row.lot_quantity)
    position_quantity = (
        Decimal(row.position_quantity) if row.position_quantity is not None else None
    )
    current = position_quantity is not None and lot_quantity == position_quantity
    return LotPositionParityAssessment(
        key=LotPositionParityKey(row.portfolio_id, row.security_id),
        epoch=int(row.epoch),
        lot_quantity=lot_quantity,
        position_quantity=position_quantity,
        status=(LotPositionParityStatus.CURRENT if current else LotPositionParityStatus.DRIFTED),
        finding_type=None if current else LOT_QUANTITY_VS_POSITION_MISMATCH,
    )
