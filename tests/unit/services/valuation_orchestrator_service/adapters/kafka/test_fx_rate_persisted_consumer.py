"""Kafka adapter tests for persisted FX correction events."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.event_mapping import EventContractValidationError
from portfolio_common.events import GOVERNED_EVENT_SCHEMA_VERSION, FxRatePersistedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.adapters.kafka import (
    fx_rate_persisted_consumer,
)
from src.services.valuation_orchestrator_service.app.infrastructure.repositories import (
    fx_revaluation_repository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def event() -> FxRatePersistedEvent:
    return FxRatePersistedEvent(
        from_currency="USD",
        to_currency="SGD",
        rate_date=date(2026, 4, 10),
        rate="1.35",
        generated_at=datetime(2026, 4, 10, 8, tzinfo=timezone.utc),
        content_hash="sha256:" + ("a" * 64),
        observation_id="sha256:" + ("b" * 64),
        event_type="FxRatePersisted",
        schema_version=GOVERNED_EVENT_SCHEMA_VERSION,
    )


@pytest.fixture
def message(event: FxRatePersistedEvent) -> MagicMock:
    result = MagicMock()
    result.value.return_value = event.model_dump_json().encode("utf-8")
    result.key.return_value = b"USD-SGD"
    result.topic.return_value = "fx_rates.persisted"
    result.partition.return_value = 0
    result.offset.return_value = 7
    result.headers.return_value = [("correlation_id", b"corr-fx")]
    return result


@pytest.fixture
def consumer() -> fx_rate_persisted_consumer.FxRatePersistedConsumer:
    return fx_rate_persisted_consumer.FxRatePersistedConsumer(
        bootstrap_servers="mock_server",
        topic="fx_rates.persisted",
        group_id="test_fx_revaluation",
        dlq_topic="dlq.persistence_service",
    )


@pytest.fixture
def dependencies():
    session = AsyncMock(spec=AsyncSession)
    session.begin.return_value = AsyncMock()
    idempotency = AsyncMock(spec=IdempotencyRepository)
    repository = AsyncMock(spec=fx_revaluation_repository.SqlAlchemyFxRevaluationRepository)
    jobs = AsyncMock(spec=ValuationJobRepository)

    async def sessions():
        yield session

    target = (
        "src.services.valuation_orchestrator_service.app.adapters.kafka.fx_rate_persisted_consumer"
    )
    with (
        patch(f"{target}.get_async_db_session", new=sessions),
        patch(f"{target}.IdempotencyRepository", return_value=idempotency),
        patch(f"{target}.SqlAlchemyFxRevaluationRepository", return_value=repository),
        patch(f"{target}.ValuationJobRepository", return_value=jobs),
    ):
        yield {
            "idempotency": idempotency,
            "repository": repository,
            "jobs": jobs,
        }


async def test_current_persisted_observation_does_not_stage_redundant_replay(
    consumer: fx_rate_persisted_consumer.FxRatePersistedConsumer,
    message: MagicMock,
    event: FxRatePersistedEvent,
    dependencies: dict,
) -> None:
    dependencies["idempotency"].claim_event_processing.return_value = True
    dependencies["repository"].latest_business_date.return_value = event.rate_date
    dependencies["repository"].find_position_keys_requiring_revaluation.return_value = []

    await consumer.process_message(message)

    dependencies["idempotency"].claim_event_processing.assert_awaited_once_with(
        event.observation_id,
        "N/A",
        "fx-rate-revaluation-trigger",
        "corr-fx",
    )
    dependencies["repository"].stage_durable_replay.assert_not_awaited()
    dependencies["repository"].find_position_keys_requiring_revaluation.assert_awaited_once()


async def test_exact_observation_replay_is_noop(
    consumer: fx_rate_persisted_consumer.FxRatePersistedConsumer,
    message: MagicMock,
    dependencies: dict,
) -> None:
    dependencies["idempotency"].claim_event_processing.return_value = False

    await consumer.process_message(message)

    dependencies["repository"].stage_durable_replay.assert_not_awaited()
    dependencies["repository"].find_position_keys_requiring_revaluation.assert_not_awaited()
    dependencies["jobs"].upsert_job.assert_not_awaited()


async def test_invalid_event_contract_raises_to_shared_recovery_boundary(
    consumer: fx_rate_persisted_consumer.FxRatePersistedConsumer,
    message: MagicMock,
    dependencies: dict,
) -> None:
    message.value.return_value = b'{"event_type":"FxRatePersisted"}'

    with pytest.raises(EventContractValidationError):
        await consumer.process_message(message)

    dependencies["idempotency"].claim_event_processing.assert_not_awaited()


async def test_missing_header_uses_source_observation_fallback_correlation(
    consumer: fx_rate_persisted_consumer.FxRatePersistedConsumer,
    message: MagicMock,
    event: FxRatePersistedEvent,
    dependencies: dict,
) -> None:
    message.headers.return_value = []
    dependencies["idempotency"].claim_event_processing.return_value = False

    await consumer.process_message(message)

    assert dependencies["idempotency"].claim_event_processing.await_args.args[3] == (
        f"FX_RATE_EVENT_{event.observation_id.removeprefix('sha256:')[:16]}"
    )
