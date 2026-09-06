"""Portfolio persistence remains on the unchanged v1 global fence contract."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.consumers.portfolio_consumer import (
    PortfolioConsumer,
)
from src.services.persistence_service.app.repositories.portfolio_repository import (
    PortfolioRepository,
)

pytestmark = pytest.mark.asyncio


async def test_portfolio_consumer_does_not_create_a_second_tenant_scoped_v1_fence() -> None:
    payload = {
        "event_type": "PortfolioCreated",
        "schema_version": "1.0",
        "correlation_id": "portfolio-correlation-1",
        "portfolio_id": "PORT-1",
        "tenant_id": "tenant-a",
        "base_currency": "USD",
        "open_date": "2025-01-01",
        "risk_exposure": "MODERATE",
        "investment_time_horizon": "LONG_TERM",
        "portfolio_type": "DISCRETIONARY",
        "booking_center_code": "SG",
        "client_id": "CLIENT-1",
        "status": "ACTIVE",
    }
    message = MagicMock()
    message.value.return_value = json.dumps(payload).encode("utf-8")
    message.topic.return_value = "portfolios.raw.received"
    message.partition.return_value = 0
    message.offset.return_value = 1
    message.headers.return_value = [("correlation_id", b"portfolio-correlation-1")]
    session = AsyncMock(spec=AsyncSession)
    session.begin.return_value = AsyncMock()

    async def sessions():
        yield session

    idempotency = AsyncMock(spec=IdempotencyRepository)
    idempotency.claim_event_processing.return_value = True
    portfolio_repository = AsyncMock(spec=PortfolioRepository)
    consumer = PortfolioConsumer(
        bootstrap_servers="mock-server",
        topic="portfolios.raw.received",
        group_id="test-group",
    )

    with (
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.get_async_db_session",
            new=sessions,
        ),
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.IdempotencyRepository",
            return_value=idempotency,
        ),
        patch(
            "src.services.persistence_service.app.consumers.portfolio_consumer.PortfolioRepository",
            return_value=portfolio_repository,
        ),
    ):
        await consumer.process_message(message)

    idempotency.claim_event_processing.assert_awaited_once_with(
        "portfolios.raw.received-0-1",
        "PORT-1",
        "persistence-portfolios",
        "portfolio-correlation-1",
    )
    portfolio_repository.create_or_update_portfolio.assert_awaited_once()
