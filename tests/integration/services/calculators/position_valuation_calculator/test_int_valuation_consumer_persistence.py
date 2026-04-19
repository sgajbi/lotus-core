from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    MarketPrice,
    OutboxEvent,
    Portfolio,
    PortfolioValuationJob,
    PositionHistory,
    ProcessedEvent,
    Transaction,
)
from portfolio_common.events import PortfolioValuationRequiredEvent
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.calculators.position_valuation_calculator.app.consumers import (
    valuation_consumer as valuation_consumer_module,
)

pytestmark = pytest.mark.asyncio


async def test_valuation_message_persists_snapshot_outbox_and_idempotency(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add_all(
        [
            Portfolio(
                portfolio_id="PORT-VAL-INT-01",
                base_currency="USD",
                open_date=date(2025, 1, 1),
                risk_exposure="MODERATE",
                investment_time_horizon="MEDIUM_TERM",
                portfolio_type="DISCRETIONARY",
                booking_center_code="SG",
                client_id="CLIENT-VAL-INT-01",
                is_leverage_allowed=False,
                status="ACTIVE",
            ),
            Instrument(
                security_id="SEC-VAL-INT-01",
                name="Valuation Test Instrument",
                isin="US-VAL-INT-01",
                asset_class="EQUITY",
                product_type="COMMON_STOCK",
                currency="USD",
            ),
            Transaction(
                transaction_id="TXN-VAL-INT-01",
                portfolio_id="PORT-VAL-INT-01",
                instrument_id="INST-VAL-INT-01",
                security_id="SEC-VAL-INT-01",
                transaction_date=datetime(2025, 8, 19, 9, 0, 0),
                transaction_type="BUY",
                quantity=Decimal("10"),
                price=Decimal("100"),
                gross_transaction_amount=Decimal("1000"),
                trade_currency="USD",
                currency="USD",
            ),
            MarketPrice(
                security_id="SEC-VAL-INT-01",
                price_date=date(2025, 8, 19),
                price=Decimal("101.50"),
                currency="USD",
            ),
            PortfolioValuationJob(
                portfolio_id="PORT-VAL-INT-01",
                security_id="SEC-VAL-INT-01",
                valuation_date=date(2025, 8, 19),
                epoch=0,
                # Direct consumer invocation should model an already-claimed worker job.
                status="PROCESSING",
                correlation_id="corr-val-int-01",
            ),
        ]
    )
    await async_db_session.commit()
    async_db_session.add(
        PositionHistory(
            transaction_id="TXN-VAL-INT-01",
            portfolio_id="PORT-VAL-INT-01",
            security_id="SEC-VAL-INT-01",
            position_date=date(2025, 8, 19),
            epoch=0,
            quantity=Decimal("10"),
            cost_basis=Decimal("1000"),
            cost_basis_local=Decimal("1000"),
        )
    )
    await async_db_session.commit()

    event = PortfolioValuationRequiredEvent(
        portfolio_id="PORT-VAL-INT-01",
        security_id="SEC-VAL-INT-01",
        valuation_date=date(2025, 8, 19),
        epoch=0,
    )
    msg = MagicMock()
    msg.value.return_value = event.model_dump_json().encode("utf-8")
    msg.key.return_value = event.portfolio_id.encode("utf-8")
    msg.topic.return_value = "valuation.job.requested"
    msg.partition.return_value = 0
    msg.offset.return_value = 7
    msg.headers.return_value = [("correlation_id", b"corr-val-int-01")]

    consumer = valuation_consumer_module.ValuationConsumer(
        bootstrap_servers="mock_server",
        topic="valuation.job.requested",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()

    async def override_session():
        yield async_db_session

    with patch(
        "src.services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.get_async_db_session",
        new=override_session,
    ):
        await consumer.process_message(msg)

    snapshots = (
        (
            await async_db_session.execute(
                select(DailyPositionSnapshot).where(
                    DailyPositionSnapshot.portfolio_id == "PORT-VAL-INT-01",
                    DailyPositionSnapshot.security_id == "SEC-VAL-INT-01",
                    DailyPositionSnapshot.date == date(2025, 8, 19),
                    DailyPositionSnapshot.epoch == 0,
                )
            )
        )
        .scalars()
        .all()
    )
    outbox_rows = (
        (
            await async_db_session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == "PORT-VAL-INT-01",
                    OutboxEvent.event_type == "DailyPositionSnapshotPersisted",
                )
            )
        )
        .scalars()
        .all()
    )
    processed_rows = (
        (
            await async_db_session.execute(
                select(ProcessedEvent).where(
                    ProcessedEvent.event_id
                    == "valuation.job.requested-0-7",
                    ProcessedEvent.service_name == "position-valuation-calculator",
                )
            )
        )
        .scalars()
        .all()
    )
    job = await async_db_session.scalar(
        select(PortfolioValuationJob).where(
            PortfolioValuationJob.portfolio_id == "PORT-VAL-INT-01",
            PortfolioValuationJob.security_id == "SEC-VAL-INT-01",
            PortfolioValuationJob.valuation_date == date(2025, 8, 19),
            PortfolioValuationJob.epoch == 0,
        )
    )

    assert len(snapshots) == 1
    assert snapshots[0].valuation_status == "VALUED_CURRENT"
    assert snapshots[0].market_value == Decimal("1015.0000000000")
    assert len(outbox_rows) == 1
    assert outbox_rows[0].correlation_id == "corr-val-int-01"
    assert len(processed_rows) == 1
    assert processed_rows[0].correlation_id == "corr-val-int-01"
    assert job is not None
    assert job.status == "COMPLETE"


async def test_valuation_message_skips_side_effects_after_losing_job_ownership(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add_all(
        [
            Portfolio(
                portfolio_id="PORT-VAL-INT-02",
                base_currency="USD",
                open_date=date(2025, 1, 1),
                risk_exposure="MODERATE",
                investment_time_horizon="MEDIUM_TERM",
                portfolio_type="DISCRETIONARY",
                booking_center_code="SG",
                client_id="CLIENT-VAL-INT-02",
                is_leverage_allowed=False,
                status="ACTIVE",
            ),
            Instrument(
                security_id="SEC-VAL-INT-02",
                name="Valuation Ownership Test Instrument",
                isin="US-VAL-INT-02",
                asset_class="EQUITY",
                product_type="COMMON_STOCK",
                currency="USD",
            ),
            Transaction(
                transaction_id="TXN-VAL-INT-02",
                portfolio_id="PORT-VAL-INT-02",
                instrument_id="INST-VAL-INT-02",
                security_id="SEC-VAL-INT-02",
                transaction_date=datetime(2025, 8, 20, 9, 0, 0),
                transaction_type="BUY",
                quantity=Decimal("10"),
                price=Decimal("100"),
                gross_transaction_amount=Decimal("1000"),
                trade_currency="USD",
                currency="USD",
            ),
            MarketPrice(
                security_id="SEC-VAL-INT-02",
                price_date=date(2025, 8, 20),
                price=Decimal("102.00"),
                currency="USD",
            ),
            PortfolioValuationJob(
                portfolio_id="PORT-VAL-INT-02",
                security_id="SEC-VAL-INT-02",
                valuation_date=date(2025, 8, 20),
                epoch=0,
                status="PROCESSING",
                correlation_id="corr-val-int-02",
            ),
        ]
    )
    await async_db_session.commit()
    async_db_session.add(
        PositionHistory(
            transaction_id="TXN-VAL-INT-02",
            portfolio_id="PORT-VAL-INT-02",
            security_id="SEC-VAL-INT-02",
            position_date=date(2025, 8, 20),
            epoch=0,
            quantity=Decimal("10"),
            cost_basis=Decimal("1000"),
            cost_basis_local=Decimal("1000"),
        )
    )
    await async_db_session.commit()

    event = PortfolioValuationRequiredEvent(
        portfolio_id="PORT-VAL-INT-02",
        security_id="SEC-VAL-INT-02",
        valuation_date=date(2025, 8, 20),
        epoch=0,
    )
    msg = MagicMock()
    msg.value.return_value = event.model_dump_json().encode("utf-8")
    msg.key.return_value = event.portfolio_id.encode("utf-8")
    msg.topic.return_value = "valuation.job.requested"
    msg.partition.return_value = 0
    msg.offset.return_value = 8
    msg.headers.return_value = [("correlation_id", b"corr-val-int-02")]

    consumer = valuation_consumer_module.ValuationConsumer(
        bootstrap_servers="mock_server",
        topic="valuation.job.requested",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def override_session():
        yield async_db_session

    original_update_job_status = valuation_consumer_module.ValuationRepository.update_job_status

    async def update_job_status_with_ownership_loss(
        self,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
        epoch: int,
        status: str,
        failure_reason: str | None = None,
    ) -> bool:
        async with session_factory() as session:
            await session.execute(
                update(PortfolioValuationJob)
                .where(
                    PortfolioValuationJob.portfolio_id == portfolio_id,
                    PortfolioValuationJob.security_id == security_id,
                    PortfolioValuationJob.valuation_date == valuation_date,
                    PortfolioValuationJob.epoch == epoch,
                )
                .values(status="COMPLETE")
            )
            await session.commit()
        return await original_update_job_status(
            self,
            portfolio_id,
            security_id,
            valuation_date,
            epoch,
            status,
            failure_reason=failure_reason,
        )

    with (
        patch(
            "src.services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.get_async_db_session",
            new=override_session,
        ),
        patch.object(
            valuation_consumer_module.ValuationRepository,
            "update_job_status",
            new=update_job_status_with_ownership_loss,
        ),
    ):
        await consumer.process_message(msg)

    snapshots = (
        (
            await async_db_session.execute(
                select(DailyPositionSnapshot).where(
                    DailyPositionSnapshot.portfolio_id == "PORT-VAL-INT-02",
                    DailyPositionSnapshot.security_id == "SEC-VAL-INT-02",
                    DailyPositionSnapshot.date == date(2025, 8, 20),
                    DailyPositionSnapshot.epoch == 0,
                )
            )
        )
        .scalars()
        .all()
    )
    outbox_rows = (
        (
            await async_db_session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == "PORT-VAL-INT-02",
                    OutboxEvent.event_type == "DailyPositionSnapshotPersisted",
                )
            )
        )
        .scalars()
        .all()
    )
    processed_rows = (
        (
            await async_db_session.execute(
                select(ProcessedEvent).where(
                    ProcessedEvent.event_id
                    == "valuation.job.requested-0-8",
                    ProcessedEvent.service_name == "position-valuation-calculator",
                )
            )
        )
        .scalars()
        .all()
    )
    job = await async_db_session.scalar(
        select(PortfolioValuationJob).where(
            PortfolioValuationJob.portfolio_id == "PORT-VAL-INT-02",
            PortfolioValuationJob.security_id == "SEC-VAL-INT-02",
            PortfolioValuationJob.valuation_date == date(2025, 8, 20),
            PortfolioValuationJob.epoch == 0,
        )
    )

    assert snapshots == []
    assert outbox_rows == []
    assert len(processed_rows) == 1
    assert processed_rows[0].correlation_id == "corr-val-int-02"
    assert job is not None
    assert job.status == "COMPLETE"
    consumer._send_to_dlq_async.assert_not_awaited()


async def test_valuation_message_allows_rearmed_same_scope_delivery_to_refresh_snapshot(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add_all(
        [
            Portfolio(
                portfolio_id="PORT-VAL-INT-03",
                base_currency="USD",
                open_date=date(2025, 1, 1),
                risk_exposure="MODERATE",
                investment_time_horizon="MEDIUM_TERM",
                portfolio_type="DISCRETIONARY",
                booking_center_code="SG",
                client_id="CLIENT-VAL-INT-03",
                is_leverage_allowed=False,
                status="ACTIVE",
            ),
            Instrument(
                security_id="CASH-VAL-INT-03",
                name="US Dollar Cash",
                isin="US-CASH-VAL-INT-03",
                asset_class="CASH",
                product_type="Cash",
                currency="USD",
            ),
            Transaction(
                transaction_id="TXN-VAL-INT-03",
                portfolio_id="PORT-VAL-INT-03",
                instrument_id="CASH-VAL-INT-03",
                security_id="CASH-VAL-INT-03",
                transaction_date=datetime(2025, 8, 21, 12, 0, 0),
                transaction_type="SELL",
                quantity=Decimal("70015"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("70015"),
                trade_currency="USD",
                currency="USD",
            ),
            MarketPrice(
                security_id="CASH-VAL-INT-03",
                price_date=date(2025, 8, 21),
                price=Decimal("1"),
                currency="USD",
            ),
        ]
    )
    await async_db_session.commit()

    async_db_session.add_all(
        [
            DailyPositionSnapshot(
                portfolio_id="PORT-VAL-INT-03",
                security_id="CASH-VAL-INT-03",
                date=date(2025, 8, 21),
                epoch=0,
                quantity=Decimal("824974.5"),
                cost_basis=Decimal("824974.5"),
                cost_basis_local=Decimal("824974.5"),
                market_price=Decimal("1"),
                market_value=Decimal("824974.5"),
                market_value_local=Decimal("824974.5"),
                unrealized_gain_loss=Decimal("0"),
                unrealized_gain_loss_local=Decimal("0"),
                valuation_status="VALUED_CURRENT",
            ),
            PortfolioValuationJob(
                portfolio_id="PORT-VAL-INT-03",
                security_id="CASH-VAL-INT-03",
                valuation_date=date(2025, 8, 21),
                epoch=0,
                status="PROCESSING",
                correlation_id="corr-val-int-03",
            ),
            ProcessedEvent(
                event_id="valuation.job.requested-0-9",
                portfolio_id="PORT-VAL-INT-03",
                service_name="position-valuation-calculator",
                correlation_id="corr-val-int-03",
            ),
        ]
    )
    await async_db_session.commit()
    async_db_session.add(
        PositionHistory(
            transaction_id="TXN-VAL-INT-03",
            portfolio_id="PORT-VAL-INT-03",
            security_id="CASH-VAL-INT-03",
            position_date=date(2025, 8, 21),
            epoch=0,
            quantity=Decimal("754959.5"),
            cost_basis=Decimal("754959.5"),
            cost_basis_local=Decimal("754959.5"),
        )
    )
    await async_db_session.commit()

    event = PortfolioValuationRequiredEvent(
        portfolio_id="PORT-VAL-INT-03",
        security_id="CASH-VAL-INT-03",
        valuation_date=date(2025, 8, 21),
        epoch=0,
    )
    msg = MagicMock()
    msg.value.return_value = event.model_dump_json().encode("utf-8")
    msg.key.return_value = event.portfolio_id.encode("utf-8")
    msg.topic.return_value = "valuation.job.requested"
    msg.partition.return_value = 0
    msg.offset.return_value = 10
    msg.headers.return_value = [("correlation_id", b"corr-val-int-03")]

    consumer = valuation_consumer_module.ValuationConsumer(
        bootstrap_servers="mock_server",
        topic="valuation.job.requested",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()

    async def override_session():
        yield async_db_session

    with patch(
        "src.services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.get_async_db_session",
        new=override_session,
    ):
        await consumer.process_message(msg)

    snapshot = await async_db_session.scalar(
        select(DailyPositionSnapshot).where(
            DailyPositionSnapshot.portfolio_id == "PORT-VAL-INT-03",
            DailyPositionSnapshot.security_id == "CASH-VAL-INT-03",
            DailyPositionSnapshot.date == date(2025, 8, 21),
            DailyPositionSnapshot.epoch == 0,
        )
    )
    processed_rows = (
        (
            await async_db_session.execute(
                select(ProcessedEvent).where(
                    ProcessedEvent.event_id.in_(
                        ["valuation.job.requested-0-9", "valuation.job.requested-0-10"]
                    ),
                    ProcessedEvent.service_name == "position-valuation-calculator",
                )
            )
        )
        .scalars()
        .all()
    )
    job = await async_db_session.scalar(
        select(PortfolioValuationJob).where(
            PortfolioValuationJob.portfolio_id == "PORT-VAL-INT-03",
            PortfolioValuationJob.security_id == "CASH-VAL-INT-03",
            PortfolioValuationJob.valuation_date == date(2025, 8, 21),
            PortfolioValuationJob.epoch == 0,
        )
    )

    assert snapshot is not None
    assert snapshot.quantity == Decimal("754959.5000000000")
    assert snapshot.cost_basis == Decimal("754959.5000000000")
    assert snapshot.market_value == Decimal("754959.5000000000")
    assert sorted(row.event_id for row in processed_rows) == [
        "valuation.job.requested-0-10",
        "valuation.job.requested-0-9",
    ]
    assert job is not None
    assert job.status == "COMPLETE"
    consumer._send_to_dlq_async.assert_not_awaited()
