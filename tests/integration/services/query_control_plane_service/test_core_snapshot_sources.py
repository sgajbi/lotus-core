from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    PipelineStageState,
    Portfolio,
    PositionHistory,
    PositionState,
    Transaction,
)
from portfolio_common.domain.holdings_reconciliation import HoldingsReconciliationScope
from portfolio_common.reconciliation_quality import (
    COMPLETE,
    FINANCIAL_RECONCILIATION_STAGE,
    UNKNOWN,
)
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.application.core_snapshot.reconciliation import (
    core_snapshot_reconciliation_evidence,
    core_snapshot_reconciliation_scopes,
)
from src.services.query_control_plane_service.app.infrastructure.core_snapshot_sources import (
    SqlAlchemyCoreSnapshotSourceReader,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]


async def test_core_snapshot_control_read_is_exact_and_set_based(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    selected_date = date(2026, 4, 10)
    selected_updated_at = datetime(2026, 4, 10, 3, tzinfo=UTC)
    async_db_session.add_all(
        [
            PipelineStageState(
                stage_name=FINANCIAL_RECONCILIATION_STAGE,
                transaction_id="reconciliation:P1:2026-04-10",
                portfolio_id="P1",
                business_date=selected_date,
                epoch=4,
                status="COMPLETED",
                updated_at=selected_updated_at,
            ),
            PipelineStageState(
                stage_name=FINANCIAL_RECONCILIATION_STAGE,
                transaction_id="reconciliation:P1:2026-04-10:old",
                portfolio_id="P1",
                business_date=selected_date,
                epoch=3,
                status="FAILED",
            ),
            PipelineStageState(
                stage_name=FINANCIAL_RECONCILIATION_STAGE,
                transaction_id="reconciliation:P2:2026-04-10",
                portfolio_id="P2",
                business_date=selected_date,
                epoch=4,
                status="FAILED",
            ),
        ]
    )
    await async_db_session.commit()

    controls = await SqlAlchemyCoreSnapshotSourceReader(
        async_db_session
    ).get_financial_reconciliation_controls(
        portfolio_id="P1",
        scopes=(
            HoldingsReconciliationScope(
                business_date=selected_date,
                epoch=4,
                latest_evidence_timestamp=datetime(2026, 4, 10, 2, tzinfo=UTC),
                source_row_count=100_000,
            ),
        ),
    )

    assert len(controls) == 1
    assert controls[0].business_date == selected_date
    assert controls[0].epoch == 4
    assert controls[0].status == "COMPLETED"
    assert controls[0].updated_at == selected_updated_at


async def test_later_valuation_state_update_does_not_stale_reconciled_position_fact(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "CORE_SNAPSHOT_RECONCILED_P1"
    security_id = "CORE_SNAPSHOT_RECONCILED_S1"
    business_date = date(2026, 4, 10)
    fact_time = datetime(2026, 4, 10, 1, tzinfo=UTC)
    control_time = fact_time + timedelta(minutes=5)
    valuation_time = control_time + timedelta(minutes=5)
    async_db_session.add_all(
        [
            Portfolio(
                tenant_id="tenant-core-snapshot-reconciliation",
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2026, 1, 1),
                risk_exposure="moderate",
                investment_time_horizon="long_term",
                portfolio_type="discretionary",
                booking_center_code="SG",
                client_id="CLIENT_CORE_SNAPSHOT_RECONCILIATION",
                status="ACTIVE",
            ),
            Instrument(
                security_id=security_id,
                name="Core Snapshot Reconciliation Equity",
                isin="XS0000001035",
                currency="USD",
                product_type="Stock",
                asset_class="Equity",
                sector="Financials",
                country_of_risk="SG",
            ),
        ]
    )
    await async_db_session.flush()
    async_db_session.add(
        Transaction(
            transaction_id="CORE-SNAPSHOT-RECONCILIATION-TXN-1",
            portfolio_id=portfolio_id,
            security_id=security_id,
            instrument_id=security_id,
            transaction_date=business_date,
            transaction_type="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            gross_transaction_amount=Decimal("1000"),
            trade_currency="USD",
            currency="USD",
        )
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id=security_id,
                transaction_id="CORE-SNAPSHOT-RECONCILIATION-TXN-1",
                position_date=business_date,
                quantity=Decimal("10"),
                cost_basis=Decimal("1000"),
                epoch=0,
                created_at=fact_time,
                updated_at=fact_time,
            ),
            PositionState(
                portfolio_id=portfolio_id,
                security_id=security_id,
                epoch=0,
                watermark_date=business_date,
                status="CURRENT",
                created_at=fact_time,
                updated_at=valuation_time,
            ),
            DailyPositionSnapshot(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=business_date,
                quantity=Decimal("10"),
                cost_basis=Decimal("1000"),
                market_price=Decimal("110"),
                market_value=Decimal("1100"),
                market_value_local=Decimal("1100"),
                valuation_status="VALUED_CURRENT",
                valuation_source_currency="USD",
                valuation_reporting_currency="USD",
                epoch=0,
                created_at=valuation_time,
                updated_at=valuation_time,
            ),
            PipelineStageState(
                stage_name=FINANCIAL_RECONCILIATION_STAGE,
                transaction_id=f"reconciliation:{portfolio_id}:{business_date.isoformat()}",
                portfolio_id=portfolio_id,
                business_date=business_date,
                epoch=0,
                status="COMPLETED",
                created_at=control_time,
                updated_at=control_time,
            ),
        ]
    )
    await async_db_session.commit()

    reader = SqlAlchemyCoreSnapshotSourceReader(async_db_session)
    rows = await reader.get_position_snapshot(
        portfolio_id=portfolio_id,
        as_of_date=business_date,
    )
    scopes = core_snapshot_reconciliation_scopes(rows)
    controls = await reader.get_financial_reconciliation_controls(
        portfolio_id=portfolio_id,
        scopes=scopes.items,
    )
    evidence = core_snapshot_reconciliation_evidence(scopes=scopes, controls=controls)

    assert len(rows) == 1
    assert rows[0].portfolio_fact_updated_at == fact_time
    assert rows[0].state_updated_at == valuation_time
    assert controls[0].updated_at == control_time
    assert scopes.items[0].latest_evidence_timestamp == fact_time
    assert evidence.status == COMPLETE

    await async_db_session.execute(
        update(PositionState)
        .where(
            PositionState.portfolio_id == portfolio_id,
            PositionState.security_id == security_id,
        )
        .values(status="REPROCESSING")
    )
    await async_db_session.commit()
    reprocessing_rows = await reader.get_position_snapshot(
        portfolio_id=portfolio_id,
        as_of_date=business_date,
    )

    assert len(reprocessing_rows) == 1
    assert reprocessing_rows[0].epoch == 0
    assert reprocessing_rows[0].state_epoch == 0
    assert reprocessing_rows[0].state_status == "REPROCESSING"

    correction_time = valuation_time + timedelta(minutes=5)
    async_db_session.add(
        PositionHistory(
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_id="CORE-SNAPSHOT-RECONCILIATION-TXN-1",
            position_date=business_date,
            quantity=Decimal("11"),
            cost_basis=Decimal("1100"),
            epoch=1,
            created_at=correction_time,
            updated_at=correction_time,
        )
    )
    await async_db_session.commit()

    history_rows = await reader.get_position_history(
        portfolio_id=portfolio_id,
        as_of_date=business_date,
    )
    mismatch_scopes = core_snapshot_reconciliation_scopes(history_rows)
    mismatch_evidence = core_snapshot_reconciliation_evidence(
        scopes=mismatch_scopes,
        controls=[],
    )

    assert len(history_rows) == 1
    assert history_rows[0].quantity == Decimal("11")
    assert history_rows[0].epoch == 1
    assert history_rows[0].state_epoch == 0
    assert mismatch_scopes.items == ()
    assert mismatch_scopes.unscoped_source_row_count == 1
    assert mismatch_evidence.status == UNKNOWN
