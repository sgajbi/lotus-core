from datetime import date
from typing import Optional

from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    Cashflow,
    Portfolio,
    PositionLotState,
    Transaction,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .identifier_normalization import normalize_security_id


def _normalized_security_ids(security_ids: list[str] | None) -> list[str] | None:
    if not security_ids:
        return None
    return [
        normalized
        for security_id in security_ids
        if (normalized := normalize_security_id(security_id))
    ]


def _normalized_lot_status(lot_status_filter: str | None) -> str:
    return (lot_status_filter or "").strip().upper()


def _requires_open_lots(*, include_closed_lots: bool, status_filter: str) -> bool:
    if status_filter == "OPEN" or (not include_closed_lots and status_filter != "CLOSED"):
        return True
    return False


def _tax_lot_status_filter(*, include_closed_lots: bool, lot_status_filter: str | None):
    status_filter = _normalized_lot_status(lot_status_filter)
    if _requires_open_lots(include_closed_lots=include_closed_lots, status_filter=status_filter):
        return PositionLotState.open_quantity > 0
    return PositionLotState.open_quantity <= 0 if status_filter == "CLOSED" else None


def _tax_lot_keyset_filter(after_sort_key: tuple[date, str] | None):
    if after_sort_key is None:
        return None
    acquisition_date, lot_id = after_sort_key
    return or_(
        PositionLotState.acquisition_date > acquisition_date,
        and_(
            PositionLotState.acquisition_date == acquisition_date,
            PositionLotState.lot_id > lot_id,
        ),
    )


def _append_optional_filter(filters: list, predicate) -> None:
    if predicate is not None:
        filters.append(predicate)


class BuyStateRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def get_position_lots(
        self, portfolio_id: str, security_id: str
    ) -> list[PositionLotState]:
        security_id = normalize_security_id(security_id)
        if not security_id:
            return []

        stmt = (
            select(PositionLotState)
            .where(
                PositionLotState.portfolio_id == portfolio_id,
                func.trim(PositionLotState.security_id) == security_id,
            )
            .order_by(PositionLotState.acquisition_date.asc(), PositionLotState.id.asc())
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def list_portfolio_tax_lots(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        security_ids: list[str] | None,
        include_closed_lots: bool,
        lot_status_filter: str | None,
        after_sort_key: tuple[date, str] | None,
        limit: int,
    ) -> list[tuple[PositionLotState, str | None]]:
        normalized_security_ids = _normalized_security_ids(security_ids)
        if security_ids and not normalized_security_ids:
            return []

        filters = [
            PositionLotState.portfolio_id == portfolio_id,
            PositionLotState.acquisition_date <= as_of_date,
        ]
        if normalized_security_ids:
            filters.append(func.trim(PositionLotState.security_id).in_(normalized_security_ids))
        _append_optional_filter(
            filters,
            _tax_lot_status_filter(
                include_closed_lots=include_closed_lots,
                lot_status_filter=lot_status_filter,
            ),
        )
        _append_optional_filter(filters, _tax_lot_keyset_filter(after_sort_key))
        stmt = (
            select(PositionLotState, Transaction.trade_currency)
            .outerjoin(
                Transaction,
                Transaction.transaction_id == PositionLotState.source_transaction_id,
            )
            .where(*filters)
            .order_by(
                PositionLotState.acquisition_date.asc(),
                PositionLotState.lot_id.asc(),
            )
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).all())

    async def get_accrued_offsets(
        self, portfolio_id: str, security_id: str
    ) -> list[AccruedIncomeOffsetState]:
        security_id = normalize_security_id(security_id)
        if not security_id:
            return []

        stmt = (
            select(AccruedIncomeOffsetState)
            .where(
                AccruedIncomeOffsetState.portfolio_id == portfolio_id,
                func.trim(AccruedIncomeOffsetState.security_id) == security_id,
            )
            .order_by(AccruedIncomeOffsetState.id.asc())
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def get_buy_cash_linkage(
        self, portfolio_id: str, transaction_id: str
    ) -> Optional[tuple[Transaction, Optional[Cashflow]]]:
        stmt = (
            select(Transaction, Cashflow)
            .outerjoin(Cashflow, Cashflow.transaction_id == Transaction.transaction_id)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_id == transaction_id,
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).first()
