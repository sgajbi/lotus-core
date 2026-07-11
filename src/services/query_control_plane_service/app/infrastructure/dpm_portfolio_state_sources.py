"""SQLAlchemy adapter for portfolio and tax-lot DPM readiness evidence."""

from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import Instrument, Portfolio, PositionLotState, Transaction
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.dpm_source_readiness import PortfolioTaxLotEvidence
from ..ports.dpm_source_readiness import DpmTaxLotPageKey


class SqlAlchemyDpmPortfolioStateReader:
    """Select bounded position-lot evidence without exposing persistence models."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        statement = (
            select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def list_portfolio_tax_lots(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        security_ids: list[str] | None,
        include_closed_lots: bool,
        lot_status_filter: str | None,
        after_sort_key: DpmTaxLotPageKey | None,
        limit: int,
    ) -> list[PortfolioTaxLotEvidence]:
        normalized_ids = _normalized_security_ids(security_ids)
        if security_ids and not normalized_ids:
            return []
        predicates = [
            PositionLotState.portfolio_id == portfolio_id,
            PositionLotState.acquisition_date <= as_of_date,
        ]
        if normalized_ids:
            predicates.append(func.trim(PositionLotState.security_id).in_(normalized_ids))
        status_predicate = _tax_lot_status_predicate(
            include_closed_lots=include_closed_lots,
            lot_status_filter=lot_status_filter,
        )
        if status_predicate is not None:
            predicates.append(status_predicate)
        if after_sort_key is not None:
            predicates.append(_tax_lot_keyset_predicate(after_sort_key))

        statement = (
            select(PositionLotState, Transaction.trade_currency)
            .outerjoin(
                Transaction,
                Transaction.transaction_id == PositionLotState.source_transaction_id,
            )
            .where(*predicates)
            .order_by(
                PositionLotState.acquisition_date.asc(),
                PositionLotState.lot_id.asc(),
            )
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [_tax_lot_evidence(lot, currency) for lot, currency in rows]

    async def list_known_instrument_security_ids(self, security_ids: list[str]) -> set[str]:
        normalized_ids = _normalized_security_ids(security_ids)
        if not normalized_ids:
            return set()
        security_id = func.trim(Instrument.security_id)
        statement = select(security_id).where(security_id.in_(normalized_ids))
        return set((await self._session.execute(statement)).scalars().all())


def _normalized_security_ids(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _tax_lot_status_predicate(*, include_closed_lots: bool, lot_status_filter: str | None) -> Any:
    status = (lot_status_filter or "").strip().upper()
    if status == "OPEN" or (not include_closed_lots and status != "CLOSED"):
        return PositionLotState.open_quantity > 0
    if status == "CLOSED":
        return PositionLotState.open_quantity <= 0
    return None


def _tax_lot_keyset_predicate(after_sort_key: DpmTaxLotPageKey) -> Any:
    acquisition_date, lot_id = after_sort_key
    return or_(
        PositionLotState.acquisition_date > acquisition_date,
        and_(
            PositionLotState.acquisition_date == acquisition_date,
            PositionLotState.lot_id > lot_id,
        ),
    )


def _tax_lot_evidence(row: Any, local_currency: str | None) -> PortfolioTaxLotEvidence:
    return PortfolioTaxLotEvidence(
        portfolio_id=row.portfolio_id,
        security_id=row.security_id.strip(),
        instrument_id=row.instrument_id.strip(),
        lot_id=row.lot_id,
        open_quantity=Decimal(str(row.open_quantity)),
        original_quantity=Decimal(str(row.original_quantity)),
        acquisition_date=row.acquisition_date,
        lot_cost_base=Decimal(str(row.lot_cost_base)),
        lot_cost_local=Decimal(str(row.lot_cost_local)),
        source_transaction_id=row.source_transaction_id,
        source_system=row.source_system,
        calculation_policy_id=row.calculation_policy_id,
        calculation_policy_version=row.calculation_policy_version,
        local_currency=local_currency,
        updated_at=row.updated_at,
    )
