"""Bound portfolio-history source scans across one dependent-day materialization command."""

from datetime import date
from typing import Literal, Protocol

from portfolio_common.database_models import PortfolioAggregationJob, PositionHistory
from portfolio_common.database_text_contract import PYTHON_STRIP_BOUNDARY_SQL
from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    column,
    func,
    insert,
    literal,
    select,
    text,
    union_all,
    values,
)
from sqlalchemy import Date as SqlDate
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import CTE

SELECTED_HISTORY_BATCH = Table(
    "_lotus_selected_history_batch",
    MetaData(),
    Column("as_of_date", SqlDate, nullable=False),
    Column("security_id", Text, nullable=False),
    Column("history_id", BigInteger, nullable=False),
    Column("business_date", SqlDate, nullable=False),
    Column("epoch", Integer, nullable=False),
    Column("quantity", Numeric, nullable=False),
    Column("source_fact", Text, nullable=False),
)


def selected_history_source_fact() -> ColumnElement[str]:
    """Canonical economic identity of one selected history row, excluding timestamps."""

    return sql_cast(
        func.jsonb_build_array(
            PositionHistory.id,
            PositionHistory.transaction_id,
            PositionHistory.position_date,
            PositionHistory.epoch,
            PositionHistory.quantity,
            PositionHistory.cost_basis,
            PositionHistory.cost_basis_local,
            PositionHistory.calculation_lineage,
        ),
        String,
    )


def normalized_history_security_id() -> ColumnElement[str]:
    """Match Python ``strip`` at the legacy history and observation boundary."""

    return func.btrim(PositionHistory.security_id, text(PYTHON_STRIP_BOUNDARY_SQL))


def ranked_selected_history_source(
    *,
    portfolio_id: str,
    as_of_date: date,
    selected_history_rows: Table | None,
) -> CTE:
    """Use the bounded batch when present, otherwise the indexed single-day source."""

    if selected_history_rows is not None:
        return (
            select(
                selected_history_rows.c.security_id,
                selected_history_rows.c.history_id,
                selected_history_rows.c.business_date,
                selected_history_rows.c.epoch,
                selected_history_rows.c.quantity,
                selected_history_rows.c.source_fact,
                literal(1).label("rank"),
            )
            .where(selected_history_rows.c.as_of_date == as_of_date)
            .cte("ranked_position_history")
        )
    security = normalized_history_security_id()
    return (
        select(
            security.label("security_id"),
            PositionHistory.id.label("history_id"),
            PositionHistory.position_date.label("business_date"),
            PositionHistory.epoch.label("epoch"),
            PositionHistory.quantity.label("quantity"),
            selected_history_source_fact().label("source_fact"),
            func.row_number()
            .over(
                partition_by=security,
                order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
            )
            .label("rank"),
        )
        .where(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.position_date <= as_of_date,
        )
        .cte("ranked_position_history")
    )


class PromoteSelectedHistoryDay(Protocol):
    async def __call__(
        self,
        portfolio_id: str,
        *,
        security_id: str,
        as_of_date: date,
        target_epoch: int,
        correlation_id: str | None,
        valuation_outcome: Literal["READY", "UNAVAILABLE"] | None,
        valuation_date: date | None,
        selected_history_rows: Table | None,
    ) -> int: ...


async def promote_selected_history_dates(
    db: AsyncSession,
    *,
    promote_one: PromoteSelectedHistoryDay,
    portfolio_id: str,
    tenant_id: str,
    security_id: str,
    as_of_dates: list[date],
    target_epoch: int,
    correlation_id: str | None,
    valuation_outcome: Literal["READY", "UNAVAILABLE"] | None,
    valuation_date: date | None,
) -> int:
    """Promote affected days with one source preparation under the caller's fence."""

    ordered_dates = sorted(set(as_of_dates))
    anchors = (
        await db.execute(
            select(
                PortfolioAggregationJob.aggregation_date,
                PortfolioAggregationJob.selected_history_sweep_epoch,
            )
            .where(
                PortfolioAggregationJob.tenant_id == tenant_id,
                PortfolioAggregationJob.portfolio_id == portfolio_id,
                PortfolioAggregationJob.aggregation_date.in_(ordered_dates),
            )
            .with_for_update()
        )
    ).all()
    if len(anchors) != len(ordered_dates):
        raise RuntimeError("Selected-history sweep requires a staged aggregation day.")
    unswept_dates = sorted(day for day, epoch in anchors if epoch < target_epoch)
    batch_rows = SELECTED_HISTORY_BATCH if len(unswept_dates) > 1 else None
    if batch_rows is not None:
        await prepare_selected_history_batch(
            db, portfolio_id=portfolio_id, as_of_dates=unswept_dates
        )
    affected = 0
    for as_of_date in ordered_dates:
        affected += await promote_one(
            portfolio_id,
            security_id=security_id,
            as_of_date=as_of_date,
            target_epoch=target_epoch,
            correlation_id=correlation_id,
            valuation_outcome=valuation_outcome,
            valuation_date=valuation_date,
            selected_history_rows=batch_rows,
        )
    return affected


async def prepare_selected_history_batch(
    db: AsyncSession,
    *,
    portfolio_id: str,
    as_of_dates: list[date],
) -> None:
    """Materialize baseline plus interval changes once in the caller's transaction."""

    await db.execute(
        text(
            "CREATE TEMP TABLE IF NOT EXISTS _lotus_selected_history_batch ("
            "as_of_date date NOT NULL, security_id text NOT NULL, "
            "history_id bigint NOT NULL, business_date date NOT NULL, "
            "epoch integer NOT NULL, quantity numeric NOT NULL, "
            "source_fact text NOT NULL) ON COMMIT DROP"
        )
    )
    await db.execute(text("TRUNCATE _lotus_selected_history_batch"))
    first_date, last_date = as_of_dates[0], as_of_dates[-1]
    security = normalized_history_security_id()
    fact = selected_history_source_fact()
    baseline_ranked = (
        select(
            security.label("security_id"),
            PositionHistory.id.label("history_id"),
            PositionHistory.position_date.label("business_date"),
            PositionHistory.epoch,
            PositionHistory.quantity,
            fact.label("source_fact"),
            func.row_number()
            .over(
                partition_by=security,
                order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
            )
            .label("rank"),
        )
        .where(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.position_date <= first_date,
        )
        .cte("batch_baseline_ranked")
    )
    baseline = select(
        *(
            baseline_ranked.c[name]
            for name in (
                "security_id",
                "history_id",
                "business_date",
                "epoch",
                "quantity",
                "source_fact",
            )
        )
    ).where(baseline_ranked.c.rank == 1)
    changes = select(
        security.label("security_id"),
        PositionHistory.id.label("history_id"),
        PositionHistory.position_date.label("business_date"),
        PositionHistory.epoch,
        PositionHistory.quantity,
        fact.label("source_fact"),
    ).where(
        PositionHistory.portfolio_id == portfolio_id,
        PositionHistory.position_date > first_date,
        PositionHistory.position_date <= last_date,
    )
    history = union_all(baseline, changes).cte("batch_position_history")
    history = history.prefix_with("MATERIALIZED", dialect="postgresql")
    affected_dates = (
        values(column("as_of_date", SqlDate), name="affected_dates")
        .data([(day,) for day in as_of_dates])
        .cte("affected_dates")
    )
    sequenced = select(
        history.c.security_id,
        history.c.history_id,
        history.c.business_date,
        history.c.epoch,
        history.c.quantity,
        history.c.source_fact,
        func.lead(history.c.business_date)
        .over(
            partition_by=history.c.security_id,
            order_by=(history.c.business_date, history.c.history_id),
        )
        .label("next_business_date"),
    ).cte("batch_sequenced_position_history")
    await db.execute(
        insert(SELECTED_HISTORY_BATCH).from_select(
            (
                "as_of_date",
                "security_id",
                "history_id",
                "business_date",
                "epoch",
                "quantity",
                "source_fact",
            ),
            select(
                affected_dates.c.as_of_date,
                sequenced.c.security_id,
                sequenced.c.history_id,
                sequenced.c.business_date,
                sequenced.c.epoch,
                sequenced.c.quantity,
                sequenced.c.source_fact,
            ).select_from(
                affected_dates.join(
                    sequenced,
                    (sequenced.c.business_date <= affected_dates.c.as_of_date)
                    & (
                        sequenced.c.next_business_date.is_(None)
                        | (sequenced.c.next_business_date > affected_dates.c.as_of_date)
                    ),
                )
            ),
        )
    )
    await db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS _lotus_selected_history_batch_asof "
            "ON _lotus_selected_history_batch (as_of_date)"
        )
    )
