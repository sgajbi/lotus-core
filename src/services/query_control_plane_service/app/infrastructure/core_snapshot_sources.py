"""SQLAlchemy source adapter for the Core portfolio snapshot application."""

from __future__ import annotations

from datetime import date

from portfolio_common.currency_codes import normalize_currency_code
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    MarketPrice,
    Portfolio,
    PositionHistory,
    PositionState,
)
from portfolio_common.identifiers import normalize_lookup_identifier
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.core_snapshot import (
    CoreSnapshotFxRate,
    CoreSnapshotInstrument,
    CoreSnapshotMarketPrice,
    CoreSnapshotPortfolio,
    CoreSnapshotPositionSource,
)


class SqlAlchemyCoreSnapshotSourceReader:
    """Resolve effective snapshot evidence using deterministic current-epoch queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_portfolio(self, portfolio_id: str) -> CoreSnapshotPortfolio | None:
        result = await self._session.execute(
            select(Portfolio).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        )
        row = result.scalars().first()
        if row is None:
            return None
        return CoreSnapshotPortfolio(
            portfolio_id=row.portfolio_id,
            base_currency=row.base_currency,
        )

    async def get_position_snapshot(
        self, *, portfolio_id: str, as_of_date: date
    ) -> list[CoreSnapshotPositionSource]:
        latest_history = self._latest_current_history(
            portfolio_id=portfolio_id, as_of_date=as_of_date
        )
        snapshot_security_id = func.trim(DailyPositionSnapshot.security_id)
        state_security_id = func.trim(PositionState.security_id)
        ranked = (
            select(
                DailyPositionSnapshot.id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=(DailyPositionSnapshot.portfolio_id, snapshot_security_id),
                    order_by=(DailyPositionSnapshot.date.desc(), DailyPositionSnapshot.id.desc()),
                )
                .label("rn"),
            )
            .join(
                latest_history,
                and_(
                    DailyPositionSnapshot.portfolio_id == latest_history.c.portfolio_id,
                    snapshot_security_id == latest_history.c.security_id,
                    DailyPositionSnapshot.epoch == latest_history.c.epoch,
                    DailyPositionSnapshot.quantity == latest_history.c.quantity,
                ),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date <= as_of_date,
                DailyPositionSnapshot.quantity != 0,
            )
            .subquery()
        )
        statement = (
            select(DailyPositionSnapshot, Instrument, PositionState)
            .join(
                ranked,
                and_(
                    DailyPositionSnapshot.id == ranked.c.snapshot_id,
                    ranked.c.rn == 1,
                ),
            )
            .join(Instrument, func.trim(Instrument.security_id) == snapshot_security_id)
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == DailyPositionSnapshot.portfolio_id,
                    state_security_id == snapshot_security_id,
                    PositionState.epoch == DailyPositionSnapshot.epoch,
                ),
            )
            .where(DailyPositionSnapshot.quantity != 0)
        )
        result = await self._session.execute(statement)
        return [
            _position_source(row, instrument, state, use_snapshot=True)
            for row, instrument, state in result.all()
        ]

    async def get_position_history(
        self, *, portfolio_id: str, as_of_date: date
    ) -> list[CoreSnapshotPositionSource]:
        history_security_id = func.trim(PositionHistory.security_id)
        state_security_id = func.trim(PositionState.security_id)
        ranked = (
            select(
                PositionHistory.id.label("position_history_id"),
                func.row_number()
                .over(
                    partition_by=history_security_id,
                    order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    PositionHistory.portfolio_id == PositionState.portfolio_id,
                    history_security_id == state_security_id,
                    PositionHistory.epoch == PositionState.epoch,
                ),
            )
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.position_date <= as_of_date,
            )
            .subquery()
        )
        statement = (
            select(PositionHistory, Instrument, PositionState)
            .join(
                ranked,
                and_(PositionHistory.id == ranked.c.position_history_id, ranked.c.rn == 1),
            )
            .join(Instrument, func.trim(Instrument.security_id) == history_security_id)
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == PositionHistory.portfolio_id,
                    state_security_id == history_security_id,
                    PositionState.epoch == PositionHistory.epoch,
                ),
            )
            .where(PositionHistory.quantity != 0)
        )
        result = await self._session.execute(statement)
        return [
            _position_source(row, instrument, state, use_snapshot=False)
            for row, instrument, state in result.all()
        ]

    async def get_instruments(self, security_ids: list[str]) -> list[CoreSnapshotInstrument]:
        normalized_ids = list(
            dict.fromkeys(
                normalized
                for value in security_ids
                if (normalized := normalize_lookup_identifier(value))
            )
        )
        if not normalized_ids:
            return []
        result = await self._session.execute(
            select(Instrument).where(func.trim(Instrument.security_id).in_(normalized_ids))
        )
        return [_instrument_record(row) for row in result.scalars().all()]

    async def get_prices(
        self, *, security_id: str, end_date: date
    ) -> list[CoreSnapshotMarketPrice]:
        normalized_id = normalize_lookup_identifier(security_id)
        if not normalized_id:
            return []
        result = await self._session.execute(
            select(MarketPrice)
            .where(
                func.trim(MarketPrice.security_id) == normalized_id,
                MarketPrice.price_date <= end_date,
            )
            .order_by(MarketPrice.price_date.asc())
        )
        return [
            CoreSnapshotMarketPrice(
                price_date=row.price_date,
                price=row.price,
                currency=row.currency,
            )
            for row in result.scalars().all()
        ]

    async def get_fx_rates(
        self,
        *,
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> list[CoreSnapshotFxRate]:
        normalized_from = normalize_currency_code(from_currency)
        normalized_to = normalize_currency_code(to_currency)
        result = await self._session.execute(
            select(FxRate)
            .where(
                func.upper(func.trim(FxRate.from_currency)) == normalized_from,
                func.upper(func.trim(FxRate.to_currency)) == normalized_to,
                FxRate.rate_date >= start_date,
                FxRate.rate_date <= end_date,
            )
            .order_by(FxRate.rate_date.asc())
        )
        return [
            CoreSnapshotFxRate(rate_date=row.rate_date, rate=row.rate)
            for row in result.scalars().all()
        ]

    @staticmethod
    def _latest_current_history(*, portfolio_id: str, as_of_date: date):
        history_security_id = func.trim(PositionHistory.security_id)
        state_security_id = func.trim(PositionState.security_id)
        ranked = (
            select(
                PositionHistory.portfolio_id.label("portfolio_id"),
                history_security_id.label("security_id"),
                PositionHistory.epoch.label("epoch"),
                PositionHistory.quantity.label("quantity"),
                func.row_number()
                .over(
                    partition_by=(PositionHistory.portfolio_id, history_security_id),
                    order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    PositionHistory.portfolio_id == PositionState.portfolio_id,
                    history_security_id == state_security_id,
                    PositionHistory.epoch == PositionState.epoch,
                ),
            )
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.position_date <= as_of_date,
            )
            .subquery()
        )
        return select(ranked).where(ranked.c.rn == 1).subquery()


def _instrument_record(row: Instrument) -> CoreSnapshotInstrument:
    return CoreSnapshotInstrument(
        security_id=normalize_lookup_identifier(row.security_id),
        name=row.name,
        currency=row.currency,
        asset_class=row.asset_class,
        sector=row.sector,
        country_of_risk=row.country_of_risk,
        isin=row.isin,
        issuer_id=row.issuer_id,
        issuer_name=row.issuer_name,
        ultimate_parent_issuer_id=row.ultimate_parent_issuer_id,
        ultimate_parent_issuer_name=row.ultimate_parent_issuer_name,
        liquidity_tier=row.liquidity_tier,
    )


def _position_source(
    row: DailyPositionSnapshot | PositionHistory,
    instrument: Instrument,
    state: PositionState,
    *,
    use_snapshot: bool,
) -> CoreSnapshotPositionSource:
    return CoreSnapshotPositionSource(
        security_id=normalize_lookup_identifier(row.security_id),
        quantity=row.quantity,
        market_value=getattr(row, "market_value", None) if use_snapshot else None,
        market_value_local=getattr(row, "market_value_local", None) if use_snapshot else None,
        cost_basis=getattr(row, "cost_basis", None),
        cost_basis_local=getattr(row, "cost_basis_local", None),
        epoch=int(state.epoch),
        source_created_at=getattr(row, "created_at", None),
        source_updated_at=getattr(row, "updated_at", None),
        state_created_at=state.created_at,
        state_updated_at=state.updated_at,
        instrument=_instrument_record(instrument),
    )
