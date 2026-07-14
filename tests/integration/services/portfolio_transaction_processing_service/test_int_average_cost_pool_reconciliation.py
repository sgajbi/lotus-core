from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    AverageCostPoolState,
    CostBasisProcessingState,
    PositionLotState,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    ReconcileAverageCostPoolsCommand,
    ReconcileAverageCostPoolsUseCase,
)
from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    AverageCostPoolRebuildPlanner,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    AverageCostPoolKey,
    AverageCostPoolReconciliationStatus,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyAverageCostPoolReconciliationAdapter,
    SqlAlchemyAverageCostPoolRepository,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
    portfolio_record,
    transaction_processing_test_context,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


async def test_historical_avco_reconciliation_repairs_stale_sources_and_is_idempotent(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-AVCO-RECONCILIATION-01"
    security_id = "FO_EQ_AVCO_RECONCILIATION_01"
    first_buy = booked_transaction_event(
        transaction_id="BUY-AVCO-RECONCILIATION-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    second_buy = booked_transaction_event(
        transaction_id="BUY-AVCO-RECONCILIATION-02",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="12",
        gross_amount="1200",
    )
    disposal = booked_transaction_event(
        transaction_id="SELL-AVCO-RECONCILIATION-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="50",
        price="15",
        gross_amount="750",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="AVCO"),
            instrument_record(
                security_id,
                name="Historical AVCO Reconciliation Equity",
                isin="SG0000000195",
                currency="USD",
            ),
            canonical_transaction_record(first_buy),
            canonical_transaction_record(second_buy),
            canonical_transaction_record(disposal),
        ]
    )
    await async_db_session.commit()
    async_db_session.add_all(
        [
            _stale_source_lot(first_buy, open_quantity="0", cost="0"),
            _stale_source_lot(second_buy, open_quantity="1", cost="12"),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    use_case = ReconcileAverageCostPoolsUseCase(
        SqlAlchemyAverageCostPoolReconciliationAdapter(
            session_factory=context.session_factory,
            rebuild_planner=AverageCostPoolRebuildPlanner(),
        )
    )

    dry_run = await use_case.execute(ReconcileAverageCostPoolsCommand(portfolio_id=portfolio_id))
    applied = await use_case.execute(
        ReconcileAverageCostPoolsCommand(apply=True, portfolio_id=portfolio_id)
    )
    repeated = await use_case.execute(
        ReconcileAverageCostPoolsCommand(apply=True, portfolio_id=portfolio_id)
    )

    assert len(dry_run.assessments) == 1
    assert dry_run.assessments[0].status is AverageCostPoolReconciliationStatus.DRIFTED
    assert dry_run.assessments[0].reason_code == "pool_state_missing"
    assert applied.assessments[0].status is AverageCostPoolReconciliationStatus.RECONCILED
    assert repeated.assessments[0].status is AverageCostPoolReconciliationStatus.CURRENT

    async with context.session_factory() as verification_session:
        source_lots = (
            (
                await verification_session.execute(
                    select(PositionLotState)
                    .where(
                        PositionLotState.portfolio_id == portfolio_id,
                        PositionLotState.security_id == security_id,
                    )
                    .order_by(PositionLotState.source_transaction_id)
                )
            )
            .scalars()
            .all()
        )
        pool = (
            await verification_session.execute(
                select(AverageCostPoolState).where(
                    AverageCostPoolState.portfolio_id == portfolio_id,
                    AverageCostPoolState.security_id == security_id,
                )
            )
        ).scalar_one()
        checkpoint = (
            await verification_session.execute(
                select(CostBasisProcessingState).where(
                    CostBasisProcessingState.portfolio_id == portfolio_id,
                    CostBasisProcessingState.security_id == security_id,
                )
            )
        ).scalar_one()

    assert [
        (
            lot.source_transaction_id,
            lot.original_quantity,
            lot.open_quantity,
            lot.lot_cost_local,
            lot.lot_cost_base,
        )
        for lot in source_lots
    ] == [
        (
            first_buy.transaction_id,
            Decimal("100"),
            Decimal("75"),
            Decimal("750"),
            Decimal("750"),
        ),
        (
            second_buy.transaction_id,
            Decimal("100"),
            Decimal("75"),
            Decimal("900"),
            Decimal("900"),
        ),
    ]
    assert pool.pool_quantity == Decimal("150")
    assert pool.pool_cost_local == Decimal("1650")
    assert pool.pool_cost_base == Decimal("1650")
    assert pool.representative_source_transaction_id == second_buy.transaction_id
    assert checkpoint.cost_basis_method == "AVCO"
    assert checkpoint.latest_transaction_id == disposal.transaction_id


async def test_historical_avco_reconciliation_rolls_back_partial_database_repair(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-AVCO-RECONCILIATION-ROLLBACK-01"
    security_id = "FO_EQ_AVCO_RECONCILIATION_ROLLBACK_01"
    buy = booked_transaction_event(
        transaction_id="BUY-AVCO-RECONCILIATION-ROLLBACK-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="AVCO"),
            instrument_record(
                security_id,
                name="Historical AVCO Reconciliation Rollback Equity",
                isin="SG0000000196",
                currency="USD",
            ),
            canonical_transaction_record(buy),
        ]
    )
    await async_db_session.commit()
    async_db_session.add(_stale_source_lot(buy, open_quantity="0", cost="0"))
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)

    class FailingAfterRebuildRepository(SqlAlchemyAverageCostPoolRepository):
        async def apply_average_cost_pool_rebuild(self, plan) -> None:
            await super().apply_average_cost_pool_rebuild(plan)
            raise RuntimeError("post-rebuild certification dependency failed")

    adapter = SqlAlchemyAverageCostPoolReconciliationAdapter(
        session_factory=context.session_factory,
        rebuild_planner=AverageCostPoolRebuildPlanner(),
        average_cost_pool_factory=FailingAfterRebuildRepository,
    )

    assessment = await adapter.reconcile(
        key=AverageCostPoolKey(portfolio_id, security_id),
        apply=True,
    )

    assert assessment.status is AverageCostPoolReconciliationStatus.FAILED
    assert assessment.reason_code == "average_cost_reconciliation_failed"
    async with context.session_factory() as verification_session:
        source_lot = (
            await verification_session.execute(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == buy.transaction_id
                )
            )
        ).scalar_one()
        pool = await verification_session.scalar(
            select(AverageCostPoolState).where(
                AverageCostPoolState.portfolio_id == portfolio_id,
                AverageCostPoolState.security_id == security_id,
            )
        )
        checkpoint = await verification_session.scalar(
            select(CostBasisProcessingState).where(
                CostBasisProcessingState.portfolio_id == portfolio_id,
                CostBasisProcessingState.security_id == security_id,
            )
        )

    assert source_lot.open_quantity == Decimal(0)
    assert source_lot.lot_cost_local == Decimal(0)
    assert source_lot.lot_cost_base == Decimal(0)
    assert pool is None
    assert checkpoint is None


def _stale_source_lot(event, *, open_quantity: str, cost: str) -> PositionLotState:
    return PositionLotState(
        lot_id=f"LOT-{event.transaction_id}",
        source_transaction_id=event.transaction_id,
        portfolio_id=event.portfolio_id,
        instrument_id=event.instrument_id,
        security_id=event.security_id,
        acquisition_date=event.transaction_date.date(),
        original_quantity=event.quantity,
        open_quantity=Decimal(open_quantity),
        lot_cost_local=Decimal(cost),
        lot_cost_base=Decimal(cost),
    )
