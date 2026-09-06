"""SQLAlchemy source adapter for the Core portfolio snapshot application."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    MarketPrice,
    PipelineStageState,
    Portfolio,
    PositionHistory,
    PositionState,
)
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.holdings_reconciliation import (
    FinancialReconciliationControl,
    HoldingsReconciliationScope,
)
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.reconciliation_quality import FINANCIAL_RECONCILIATION_STAGE
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.core_snapshot import (
    CoreSnapshotFxRate,
    CoreSnapshotInstrument,
    CoreSnapshotMarketPrice,
    CoreSnapshotPortfolio,
    CoreSnapshotPositionSource,
)


class SqlAlchemyCoreSnapshotSourceReader:
    """Resolve latest financial facts with their independently persisted state epoch."""

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
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def get_position_snapshot(
        self, *, portfolio_id: str, as_of_date: date
    ) -> list[CoreSnapshotPositionSource]:
        latest_history = self._latest_position_history(
            portfolio_id=portfolio_id, as_of_date=as_of_date
        )
        snapshot_security_id = func.trim(DailyPositionSnapshot.security_id)
        state_security_id = func.trim(PositionState.security_id)
        ranked = (
            select(
                DailyPositionSnapshot.id.label("snapshot_id"),
                DailyPositionSnapshot.portfolio_id.label("portfolio_id"),
                snapshot_security_id.label("security_id"),
                DailyPositionSnapshot.epoch.label("epoch"),
                DailyPositionSnapshot.quantity.label("quantity"),
                func.row_number()
                .over(
                    partition_by=(
                        DailyPositionSnapshot.portfolio_id,
                        snapshot_security_id,
                        DailyPositionSnapshot.epoch,
                        DailyPositionSnapshot.quantity,
                    ),
                    order_by=(DailyPositionSnapshot.date.desc(), DailyPositionSnapshot.id.desc()),
                )
                .label("rn"),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date <= as_of_date,
                DailyPositionSnapshot.quantity != 0,
            )
            .subquery()
        )
        statement = (
            select(
                DailyPositionSnapshot,
                Instrument,
                PositionState,
                latest_history.c.security_id,
                latest_history.c.epoch,
                latest_history.c.portfolio_business_date,
                latest_history.c.cost_basis,
                latest_history.c.cost_basis_local,
                latest_history.c.source_created_at,
                latest_history.c.source_updated_at,
            )
            .select_from(latest_history)
            .outerjoin(
                ranked,
                and_(
                    ranked.c.portfolio_id == latest_history.c.portfolio_id,
                    ranked.c.security_id == latest_history.c.security_id,
                    ranked.c.epoch == latest_history.c.epoch,
                    ranked.c.quantity == latest_history.c.quantity,
                    ranked.c.rn == 1,
                ),
            )
            .outerjoin(
                DailyPositionSnapshot,
                DailyPositionSnapshot.id == ranked.c.snapshot_id,
            )
            .outerjoin(
                Instrument,
                func.trim(Instrument.security_id) == latest_history.c.security_id,
            )
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == latest_history.c.portfolio_id,
                    state_security_id == latest_history.c.security_id,
                ),
            )
            .where(latest_history.c.quantity != 0)
        )
        result = await self._session.execute(statement)
        selected_rows = result.all()
        expected_security_ids = {
            normalize_lookup_identifier(selected[3]) for selected in selected_rows
        }
        represented_security_ids = {
            normalize_lookup_identifier(row.security_id)
            for row, instrument, *_ in selected_rows
            if row is not None and instrument is not None
        }
        if (
            "" in expected_security_ids
            or len(selected_rows) != len(expected_security_ids)
            or represented_security_ids != expected_security_ids
        ):
            # The application interprets an empty current snapshot as an explicit
            # history fallback, which cannot claim current market-data readiness.
            return []
        return [
            _position_source(
                row,
                instrument,
                state,
                use_snapshot=True,
                portfolio_fact_epoch=portfolio_fact_epoch,
                portfolio_business_date=portfolio_business_date,
                portfolio_cost_basis=portfolio_cost_basis,
                portfolio_cost_basis_local=portfolio_cost_basis_local,
                portfolio_fact_created_at=source_created_at,
                portfolio_fact_updated_at=source_updated_at,
            )
            for (
                row,
                instrument,
                state,
                _expected_security_id,
                portfolio_fact_epoch,
                portfolio_business_date,
                portfolio_cost_basis,
                portfolio_cost_basis_local,
                source_created_at,
                source_updated_at,
            ) in selected_rows
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
                ),
            )
            .where(PositionHistory.quantity != 0)
        )
        result = await self._session.execute(statement)
        return [
            _position_source(row, instrument, state, use_snapshot=False)
            for row, instrument, state in result.all()
        ]

    async def get_financial_reconciliation_controls(
        self,
        *,
        portfolio_id: str,
        scopes: tuple[HoldingsReconciliationScope, ...],
    ) -> list[FinancialReconciliationControl]:
        """Read exact portfolio-day/epoch controls in one set-based query."""

        scope_keys = sorted({(scope.business_date, scope.epoch) for scope in scopes})
        if not scope_keys:
            return []
        statement = select(PipelineStageState).where(
            PipelineStageState.stage_name == FINANCIAL_RECONCILIATION_STAGE,
            PipelineStageState.portfolio_id == portfolio_id,
            tuple_(PipelineStageState.business_date, PipelineStageState.epoch).in_(scope_keys),
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [
            FinancialReconciliationControl(
                business_date=row.business_date,
                epoch=row.epoch,
                status=row.status,
                updated_at=row.updated_at,
            )
            for row in rows
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
                evidence_timestamp=_row_evidence_timestamp(row),
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
            .order_by(FxRate.rate_date.asc(), FxRate.id.asc())
        )
        return [
            CoreSnapshotFxRate(
                rate_date=row.rate_date,
                rate=row.rate,
                evidence_timestamp=_row_evidence_timestamp(row),
            )
            for row in result.scalars().all()
        ]

    @staticmethod
    def _latest_position_history(*, portfolio_id: str, as_of_date: date):
        history_security_id = func.trim(PositionHistory.security_id)
        ranked = (
            select(
                PositionHistory.portfolio_id.label("portfolio_id"),
                history_security_id.label("security_id"),
                PositionHistory.epoch.label("epoch"),
                PositionHistory.quantity.label("quantity"),
                PositionHistory.cost_basis.label("cost_basis"),
                PositionHistory.cost_basis_local.label("cost_basis_local"),
                PositionHistory.position_date.label("portfolio_business_date"),
                PositionHistory.created_at.label("source_created_at"),
                PositionHistory.updated_at.label("source_updated_at"),
                func.row_number()
                .over(
                    partition_by=(PositionHistory.portfolio_id, history_security_id),
                    order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
                )
                .label("rn"),
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
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _position_source(
    row: DailyPositionSnapshot | PositionHistory,
    instrument: Instrument,
    state: PositionState,
    *,
    use_snapshot: bool,
    portfolio_fact_epoch: int | None = None,
    portfolio_business_date: date | None = None,
    portfolio_cost_basis: Decimal | None = None,
    portfolio_cost_basis_local: Decimal | None = None,
    portfolio_fact_created_at: datetime | None = None,
    portfolio_fact_updated_at: datetime | None = None,
) -> CoreSnapshotPositionSource:
    return CoreSnapshotPositionSource(
        security_id=normalize_lookup_identifier(row.security_id),
        quantity=row.quantity,
        market_price=getattr(row, "market_price", None) if use_snapshot else None,
        market_value=getattr(row, "market_value", None) if use_snapshot else None,
        market_value_local=getattr(row, "market_value_local", None) if use_snapshot else None,
        cost_basis=(portfolio_cost_basis if use_snapshot else getattr(row, "cost_basis", None)),
        cost_basis_local=(
            portfolio_cost_basis_local if use_snapshot else getattr(row, "cost_basis_local", None)
        ),
        epoch=int(portfolio_fact_epoch if portfolio_fact_epoch is not None else row.epoch),
        state_epoch=int(state.epoch),
        state_status=str(state.status).strip().upper(),
        source_created_at=getattr(row, "created_at", None),
        source_updated_at=getattr(row, "updated_at", None),
        state_created_at=state.created_at,
        state_updated_at=state.updated_at,
        instrument=_instrument_record(instrument),
        business_date=(row.date if use_snapshot else row.position_date),
        valuation_status=getattr(row, "valuation_status", None) if use_snapshot else None,
        valuation_source_currency=(
            getattr(row, "valuation_source_currency", None) if use_snapshot else None
        ),
        valuation_reporting_currency=(
            getattr(row, "valuation_reporting_currency", None) if use_snapshot else None
        ),
        valuation_fx_rate_date=(
            getattr(row, "valuation_fx_rate_date", None) if use_snapshot else None
        ),
        valuation_fx_rate=(getattr(row, "valuation_fx_rate", None) if use_snapshot else None),
        portfolio_fact_created_at=(
            portfolio_fact_created_at if use_snapshot else getattr(row, "created_at", None)
        ),
        portfolio_fact_updated_at=(
            portfolio_fact_updated_at if use_snapshot else getattr(row, "updated_at", None)
        ),
        portfolio_business_date=(
            portfolio_business_date if use_snapshot else getattr(row, "position_date", None)
        ),
    )


def _row_evidence_timestamp(row: object) -> datetime | None:
    timestamps = tuple(
        value
        for attribute in ("created_at", "updated_at")
        if isinstance((value := getattr(row, attribute, None)), datetime)
    )
    return max(timestamps, default=None)
