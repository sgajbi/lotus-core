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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
                status="PENDING",
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
    msg.topic.return_value = "valuation_required"
    msg.partition.return_value = 0
    msg.offset.return_value = 7
    msg.headers.return_value = [("correlation_id", b"corr-val-int-01")]

    consumer = valuation_consumer_module.ValuationConsumer(
        bootstrap_servers="mock_server",
        topic="valuation_required",
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
                    ProcessedEvent.event_id == "valuation_required-0-7",
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
