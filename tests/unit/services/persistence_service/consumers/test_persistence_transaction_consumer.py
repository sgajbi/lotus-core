# tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py
import io
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.domain.transaction.fx_source_admission import IncompleteFxSourceError
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import TransactionSemanticConflictError
from portfolio_common.idempotency_repository import (
    IdempotencyRepository,
    SemanticEventClaimOutcome,
)
from portfolio_common.logging_utils import RedactingJsonFormatter, correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.consumers.transaction_consumer import (
    PortfolioNotFoundError,
    TransactionPersistenceConsumer,
)
from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
    TransactionReferenceAvailability,
    TransactionWriteOutcome,
)

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio
TRANSACTION_CONSUMER_LOGGER = "src.services.persistence_service.app.consumers.transaction_consumer"
BASE_CONSUMER_LOGGER = "src.services.persistence_service.app.consumers.base_consumer"


class _OtherEvent(BaseModel):
    pass


@pytest.fixture
def transaction_consumer():
    """Provides an instance of the consumer for testing."""
    return TransactionPersistenceConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.raw.received",
        group_id="test_group",
        dlq_topic="dlq.persistence_service",
    )


@pytest.fixture
def valid_transaction_event():
    """Provides a valid TransactionEvent object."""
    return TransactionEvent(
        transaction_id="UNIT_TEST_01",
        portfolio_id="PORT_UT_01",
        tenant_id="tenant-test",
        instrument_id="INST_UT_01",
        security_id="SEC_UT_01",
        transaction_date="2025-07-31T12:00:00Z",
        transaction_type="BUY",
        quantity=100,
        price=50,
        gross_transaction_amount=5000,
        trade_currency="USD",
        currency="USD",
    )


@pytest.fixture
def mock_kafka_message(valid_transaction_event: TransactionEvent):
    """Creates a mock Kafka message containing a valid transaction."""
    mock_message = MagicMock()
    mock_message.value.return_value = valid_transaction_event.model_dump_json().encode("utf-8")
    mock_message.key.return_value = "test_key".encode("utf-8")
    mock_message.error.return_value = None
    mock_message.topic.return_value = "transactions.raw.received"
    mock_message.partition.return_value = 0
    mock_message.offset.return_value = 1
    mock_message.headers.return_value = [("correlation_id", b"test-corr-id")]
    return mock_message


@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_repo = AsyncMock(spec=TransactionDBRepository)
    mock_repo.create_or_update_transaction.return_value = TransactionWriteOutcome(
        transaction=MagicMock(),
        inserted=True,
    )
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_repo.resolve_portfolio_tenant.return_value = "tenant-test"

    mock_db_session = AsyncMock(spec=AsyncSession)
    # FIX: The `begin()` method must return an async context manager.
    # An AsyncMock can be used as one directly.
    mock_db_session.begin.return_value = AsyncMock()

    async def get_session_gen():
        yield mock_db_session

    with (
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.persistence_service.app.consumers.transaction_consumer.TransactionDBRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.OutboxRepository",
            return_value=mock_outbox_repo,
        ),
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
    ):
        yield {
            "db_session": mock_db_session,
            "repo": mock_repo,
            "outbox_repo": mock_outbox_repo,
            "idempotency_repo": mock_idempotency_repo,
        }


@pytest.mark.parametrize(
    "claim",
    [SemanticEventClaimOutcome.PHYSICAL_DUPLICATE, SemanticEventClaimOutcome.SEMANTIC_DUPLICATE],
)
async def test_incomplete_historical_fx_duplicate_skips_fresh_admission(
    transaction_consumer, valid_transaction_event, mock_kafka_message, mock_dependencies, claim
) -> None:
    event = valid_transaction_event.model_copy(
        update={
            "transaction_type": "FX_FORWARD",
            "component_type": "FX_CONTRACT_CLOSE",
            "fx_realized_pnl_mode": "UPSTREAM_PROVIDED",
        }
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode()
    mock_dependencies["idempotency_repo"].claim_semantic_event_processing.return_value = claim
    await transaction_consumer.process_message(mock_kafka_message)
    mock_dependencies["repo"].qualifies_identical_durable_replay.assert_not_awaited()
    mock_dependencies["repo"].create_or_update_transaction.assert_not_awaited()
    mock_dependencies["outbox_repo"].create_outbox_event.assert_not_awaited()


async def test_fresh_incomplete_fx_refuses_after_claim_inside_rollback_uow(
    transaction_consumer, valid_transaction_event, mock_kafka_message, mock_dependencies
) -> None:
    event = valid_transaction_event.model_copy(
        update={
            "transaction_type": "FX_FORWARD",
            "component_type": "FX_CONTRACT_CLOSE",
            "fx_realized_pnl_mode": "UPSTREAM_PROVIDED",
        }
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode()
    mock_dependencies[
        "idempotency_repo"
    ].claim_semantic_event_processing.return_value = SemanticEventClaimOutcome.CLAIMED
    mock_dependencies["repo"].qualifies_identical_durable_replay.return_value = False
    with pytest.raises(IncompleteFxSourceError) as raised:
        await transaction_consumer.process_message(mock_kafka_message)
    assert raised.value.missing_fields == ("realized_fx_pnl_local", "realized_fx_pnl_base")
    mock_dependencies["idempotency_repo"].claim_semantic_event_processing.assert_awaited_once()
    exit_args = mock_dependencies["db_session"].begin.return_value.__aexit__.await_args.args
    assert exit_args[0] is IncompleteFxSourceError
    mock_dependencies["repo"].create_or_update_transaction.assert_not_awaited()
    mock_dependencies["outbox_repo"].create_outbox_event.assert_not_awaited()


async def test_incomplete_historical_fx_exact_durable_replay_after_fence_expiry(
    transaction_consumer, valid_transaction_event, mock_kafka_message, mock_dependencies
) -> None:
    event = valid_transaction_event.model_copy(
        update={
            "transaction_type": "FX_FORWARD",
            "component_type": "FX_CONTRACT_CLOSE",
            "fx_realized_pnl_mode": "UPSTREAM_PROVIDED",
        }
    )
    mock_kafka_message.value.return_value = event.model_dump_json().encode()
    mock_dependencies[
        "idempotency_repo"
    ].claim_semantic_event_processing.return_value = SemanticEventClaimOutcome.CLAIMED
    mock_dependencies["repo"].qualifies_identical_durable_replay.return_value = True
    await transaction_consumer.process_message(mock_kafka_message)
    mock_dependencies["repo"].qualifies_identical_durable_replay.assert_awaited_once()
    mock_dependencies["repo"].create_or_update_transaction.assert_not_awaited()
    mock_dependencies["outbox_repo"].create_outbox_event.assert_not_awaited()


async def test_process_message_success(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    """
    GIVEN a valid transaction message
    WHEN the process_message method is called
    THEN it should call the repository to save the transaction
    AND publish a completion event.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_repo.resolve_transaction_reference_availability.return_value = (
        TransactionReferenceAvailability(
            portfolio_exists=True,
            instrument_exists=True,
            cash_account_exists=None,
        )
    )
    mock_idempotency_repo.claim_semantic_event_processing.return_value = (
        SemanticEventClaimOutcome.CLAIMED
    )

    # Use patch.object for robust mocking
    with patch.object(
        transaction_consumer, "_send_to_dlq_async", new_callable=AsyncMock
    ) as mock_send_to_dlq:
        # ACT
        await transaction_consumer.process_message(mock_kafka_message)

        # ASSERT
        mock_repo.create_or_update_transaction.assert_called_once()
        mock_repo.resolve_transaction_reference_availability.assert_awaited_once_with(
            portfolio_id="PORT_UT_01",
            tenant_id="tenant-test",
            security_id="SEC_UT_01",
            cash_account_id=None,
            cash_security_id=None,
            as_of_date=valid_transaction_event.transaction_date.date(),
        )
        mock_outbox_repo.create_outbox_event.assert_called_once()
        assert mock_outbox_repo.create_outbox_event.call_args.kwargs["partition_key"].value == (
            "PORT_UT_01|SEC_UT_01"
        )
        assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
            "test-corr-id"
        )
        semantic_claim = mock_idempotency_repo.claim_semantic_event_processing.await_args.kwargs
        assert semantic_claim == {
            "event_id": "UNIT_TEST_01",
            "portfolio_id": "PORT_UT_01",
            "service_name": "persistence-transactions",
            "semantic_key": "transaction-persistence:v1:tenant-test:UNIT_TEST_01",
            "payload_fingerprint": semantic_claim["payload_fingerprint"],
            "correlation_id": "test-corr-id",
            "tenant_id": "tenant-test",
        }
        assert semantic_claim["payload_fingerprint"].startswith("sha256:")
        mock_send_to_dlq.assert_not_called()


async def test_process_message_validation_log_excludes_rejected_input(
    transaction_consumer: TransactionPersistenceConsumer,
) -> None:
    marker = "SYNTHETIC_REDACTION_PROBE_7X"
    correlation_id = "synthetic-review-correlation"
    message = MagicMock()
    message.value.return_value = json.dumps(
        {"password": marker, "correlation_id": correlation_id}
    ).encode("utf-8")
    message.key.return_value = b"synthetic-invalid-transaction"
    message.error.return_value = None
    message.topic.return_value = "transactions.raw.received"
    message.partition.return_value = 0
    message.offset.return_value = 496
    message.headers.return_value = []

    session_requested = False

    async def unexpected_session():
        nonlocal session_requested
        session_requested = True
        raise AssertionError("Validation rejection must happen before database access")
        yield  # pragma: no cover

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        RedactingJsonFormatter(
            "%(message)s %(event_name)s %(operation)s %(status)s %(reason_code)s "
            "%(message_correlation_id)s %(validation_error_count)s "
            "%(validation_error_locations)s %(validation_error_types)s"
        )
    )
    consumer_logger = logging.getLogger(BASE_CONSUMER_LOGGER)

    with (
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.get_async_db_session",
            new=unexpected_session,
        ),
        patch.object(consumer_logger, "handlers", [handler]),
        patch.object(consumer_logger, "propagate", False),
        patch.object(consumer_logger, "level", logging.ERROR),
        pytest.raises(ValidationError) as exc_info,
    ):
        await transaction_consumer.process_message(message)

    emitted = stream.getvalue()
    assert marker in str(exc_info.value)
    assert marker not in emitted
    assert session_requested is False

    record = json.loads(emitted)
    assert record["message"] == "Message validation failed."
    assert record["event_name"] == "persistence.message.validation"
    assert record["operation"] == "persistence_consume"
    assert record["status"] == "rejected"
    assert record["reason_code"] == "schema_validation_failed"
    assert record["message_correlation_id"] == correlation_id
    assert record["validation_error_count"] > 0
    assert "missing" in record["validation_error_types"]
    assert "transaction_id" in record["validation_error_locations"]


async def test_process_message_json_decode_log_excludes_rejected_document(
    transaction_consumer: TransactionPersistenceConsumer,
) -> None:
    marker = "SYNTHETIC_REDACTION_PROBE_7X"
    message = MagicMock()
    message.value.return_value = f'{{"password":"{marker}",'.encode()
    message.key.return_value = b"synthetic-invalid-json"
    message.error.return_value = None
    message.topic.return_value = "transactions.raw.received"
    message.partition.return_value = 0
    message.offset.return_value = 497
    message.headers.return_value = [("correlation_id", b"header-correlation")]

    session_requested = False

    async def unexpected_session():
        nonlocal session_requested
        session_requested = True
        raise AssertionError("JSON rejection must happen before database access")
        yield  # pragma: no cover

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingJsonFormatter())
    consumer_logger = logging.getLogger(BASE_CONSUMER_LOGGER)

    with (
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.get_async_db_session",
            new=unexpected_session,
        ),
        patch.object(consumer_logger, "handlers", [handler]),
        patch.object(consumer_logger, "propagate", False),
        patch.object(consumer_logger, "level", logging.ERROR),
        pytest.raises(json.JSONDecodeError) as exc_info,
    ):
        await transaction_consumer.process_message(message)

    emitted = stream.getvalue()
    assert marker in exc_info.value.doc
    assert marker not in emitted
    assert session_requested is False

    record = json.loads(emitted)
    assert record["reason_code"] == "json_decode_failed"
    assert record["message_correlation_id"] == "header-correlation"
    assert record["error_type"] == "JSONDecodeError"
    assert record["json_line"] == 1
    assert record["json_column"] > 0
    assert record["json_position"] > 0


async def test_semantic_identity_requires_admitted_transaction(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
) -> None:
    for invalid_event in (
        _OtherEvent(),
        valid_transaction_event.model_copy(update={"tenant_id": None}),
    ):
        with pytest.raises(TypeError, match="requires an admitted tenant"):
            transaction_consumer.semantic_idempotency_identity(invalid_event)


async def test_prepare_event_rejects_non_transaction(
    transaction_consumer: TransactionPersistenceConsumer,
) -> None:
    with pytest.raises(TypeError, match="requires a transaction event"):
        await TransactionPersistenceConsumer.prepare_event.__wrapped__(
            transaction_consumer,
            AsyncMock(spec=AsyncSession),
            _OtherEvent(),
        )


@pytest.mark.parametrize(
    ("source_tenant_id", "expected_error"),
    [
        (None, PortfolioNotFoundError),
        ("tenant-other", ValueError),
    ],
)
async def test_prepare_event_fails_closed_without_matching_tenant_authority(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
    mock_dependencies: dict,
    source_tenant_id: str | None,
    expected_error: type[Exception],
) -> None:
    mock_dependencies["repo"].resolve_portfolio_tenant.return_value = source_tenant_id

    with pytest.raises(expected_error):
        await TransactionPersistenceConsumer.prepare_event.__wrapped__(
            transaction_consumer,
            AsyncMock(spec=AsyncSession),
            valid_transaction_event,
        )


@pytest.mark.parametrize(
    ("rate", "producer_origin", "expected_origin"),
    [
        ("2.0", None, "SOURCE_BOOKED"),
        ("2.0", "REFERENCE_DERIVED", "SOURCE_BOOKED"),
        ("2.0", "LEGACY_UNKNOWN", "SOURCE_BOOKED"),
        ("2.0", "producer-garbage", "SOURCE_BOOKED"),
        (None, "SOURCE_BOOKED", None),
    ],
)
async def test_prepare_event_stamps_server_owned_raw_fx_origin(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
    mock_dependencies: dict,
    rate: str | None,
    producer_origin: str | None,
    expected_origin: str | None,
) -> None:
    incoming = valid_transaction_event.model_copy(
        update={
            "transaction_fx_rate": rate,
            "transaction_fx_rate_origin": producer_origin,
        }
    )

    admitted = await TransactionPersistenceConsumer.prepare_event.__wrapped__(
        transaction_consumer,
        AsyncMock(spec=AsyncSession),
        incoming,
    )

    assert admitted.transaction_fx_rate_origin == expected_origin


async def test_process_message_skips_identical_semantic_replay(
    transaction_consumer: TransactionPersistenceConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
) -> None:
    mock_dependencies[
        "idempotency_repo"
    ].claim_semantic_event_processing.return_value = SemanticEventClaimOutcome.SEMANTIC_DUPLICATE

    await transaction_consumer.process_message(mock_kafka_message)

    mock_dependencies["repo"].create_or_update_transaction.assert_not_awaited()
    mock_dependencies["outbox_repo"].create_outbox_event.assert_not_awaited()


async def test_process_message_skips_outbox_for_durable_ledger_replay_after_claim_expiry(
    transaction_consumer: TransactionPersistenceConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
) -> None:
    mock_dependencies[
        "repo"
    ].resolve_transaction_reference_availability.return_value = TransactionReferenceAvailability(
        portfolio_exists=True,
        instrument_exists=True,
        cash_account_exists=None,
    )
    mock_dependencies[
        "idempotency_repo"
    ].claim_semantic_event_processing.return_value = SemanticEventClaimOutcome.CLAIMED
    mock_dependencies["repo"].create_or_update_transaction.return_value = TransactionWriteOutcome(
        transaction=MagicMock(), inserted=False
    )

    await transaction_consumer.process_message(mock_kafka_message)

    mock_dependencies["repo"].create_or_update_transaction.assert_awaited_once()
    mock_dependencies["outbox_repo"].create_outbox_event.assert_not_awaited()


async def test_process_message_rejects_materially_changed_semantic_replay(
    transaction_consumer: TransactionPersistenceConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
) -> None:
    idempotency = mock_dependencies["idempotency_repo"]
    idempotency.claim_semantic_event_processing.return_value = (
        SemanticEventClaimOutcome.SEMANTIC_CONFLICT
    )
    idempotency.resolve_semantic_payload_fingerprint.return_value = "sha256:" + "a" * 64

    with pytest.raises(
        TransactionSemanticConflictError,
        match="TRANSACTION_SEMANTIC_CONFLICT",
    ) as exc_info:
        await transaction_consumer.process_message(mock_kafka_message)

    assert exc_info.value.existing_payload_fingerprint == "sha256:" + "a" * 64
    assert exc_info.value.incoming_payload_fingerprint.startswith("sha256:")
    mock_dependencies["repo"].create_or_update_transaction.assert_not_awaited()
    mock_dependencies["outbox_repo"].create_outbox_event.assert_not_awaited()


async def test_legacy_v1_message_resolves_tenant_before_idempotency_and_persistence(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
    mock_dependencies: dict,
) -> None:
    payload = valid_transaction_event.model_dump(exclude={"tenant_id"}, mode="json")
    message = MagicMock()
    message.value.return_value = json.dumps(payload).encode("utf-8")
    message.topic.return_value = "transactions.raw.received"
    message.partition.return_value = 0
    message.offset.return_value = 7
    message.headers.return_value = [("correlation_id", b"legacy-corr")]
    mock_repo = mock_dependencies["repo"]
    mock_repo.resolve_transaction_reference_availability.return_value = (
        TransactionReferenceAvailability(
            portfolio_exists=True,
            instrument_exists=True,
            cash_account_exists=None,
        )
    )
    mock_dependencies[
        "idempotency_repo"
    ].claim_semantic_event_processing.return_value = SemanticEventClaimOutcome.CLAIMED

    await transaction_consumer.process_message(message)

    mock_repo.resolve_portfolio_tenant.assert_awaited_once_with("PORT_UT_01")
    persisted_event = mock_repo.create_or_update_transaction.await_args.args[0]
    assert persisted_event.tenant_id == "tenant-test"
    semantic_claim = mock_dependencies[
        "idempotency_repo"
    ].claim_semantic_event_processing.await_args.kwargs
    assert semantic_claim["event_id"] == "UNIT_TEST_01"
    assert semantic_claim["semantic_key"] == ("transaction-persistence:v1:tenant-test:UNIT_TEST_01")
    assert semantic_claim["tenant_id"] == "tenant-test"
    assert semantic_claim["correlation_id"] == "legacy-corr"


async def test_persisted_linked_transaction_retains_group_partition_identity(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
) -> None:
    linked_event = valid_transaction_event.model_copy(
        update={"linked_transaction_group_id": "CA-GROUP-1"}
    )

    outbox_event = transaction_consumer.get_outbox_event(linked_event)

    assert outbox_event is not None
    assert outbox_event["partition_key"].value == ("PORT_UT_01|transaction-group|CA-GROUP-1")


async def test_persisted_transaction_publishes_canonical_identity(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
) -> None:
    event = TransactionEvent.model_validate(
        valid_transaction_event.model_dump()
        | {
            "transaction_id": "  UNIT_TEST_01  ",
            "portfolio_id": "  PORT_UT_01  ",
            "instrument_id": "  INST_UT_01  ",
            "security_id": "  SEC_UT_01  ",
        }
    )

    outbox_event = transaction_consumer.get_outbox_event(event)

    assert outbox_event is not None
    assert outbox_event["aggregate_id"] == "PORT_UT_01"
    assert outbox_event["partition_key"].value == "PORT_UT_01|SEC_UT_01"
    assert outbox_event["payload"]["transaction_id"] == "UNIT_TEST_01"
    assert outbox_event["payload"]["portfolio_id"] == "PORT_UT_01"
    assert "tenant_id" not in outbox_event["payload"]


async def test_process_message_uses_header_correlation_on_direct_path(
    transaction_consumer: TransactionPersistenceConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_repo.resolve_transaction_reference_availability.return_value = (
        TransactionReferenceAvailability(
            portfolio_exists=True,
            instrument_exists=True,
            cash_account_exists=None,
        )
    )
    mock_idempotency_repo.claim_semantic_event_processing.return_value = (
        SemanticEventClaimOutcome.CLAIMED
    )

    token = correlation_id_var.set("<not-set>")
    try:
        await transaction_consumer.process_message(mock_kafka_message)
    finally:
        correlation_id_var.reset(token)

    assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
        "test-corr-id"
    )
    semantic_claim = mock_idempotency_repo.claim_semantic_event_processing.await_args.kwargs
    assert semantic_claim["event_id"] == "UNIT_TEST_01"
    assert semantic_claim["tenant_id"] == "tenant-test"
    assert semantic_claim["correlation_id"] == "test-corr-id"


# --- REVISED TEST ---
async def test_handle_persistence_retries_and_succeeds(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a transaction for a portfolio that initially does not exist
    WHEN handle_persistence is called
    THEN it should retry and succeed once the portfolio exists.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]

    # Simulate portfolio not found on first call, but found on the second
    mock_repo.resolve_transaction_reference_availability.side_effect = [
        TransactionReferenceAvailability(
            portfolio_exists=False,
            instrument_exists=True,
            cash_account_exists=None,
        ),
        TransactionReferenceAvailability(
            portfolio_exists=True,
            instrument_exists=True,
            cash_account_exists=None,
        ),
    ]

    # ACT
    # This call will invoke the retry logic internally and should complete without error
    await transaction_consumer.handle_persistence(AsyncMock(), valid_transaction_event)

    # ASSERT
    # Verify the check was called twice (initial attempt + 1 retry)
    assert mock_repo.resolve_transaction_reference_availability.await_count == 2

    # Verify the transaction was created only on the successful attempt
    mock_repo.create_or_update_transaction.assert_awaited_once_with(valid_transaction_event)


async def test_handle_persistence_allows_provisional_raw_landing_for_missing_instrument(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
    mock_dependencies: dict,
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.WARNING, logger=TRANSACTION_CONSUMER_LOGGER)
    mock_repo = mock_dependencies["repo"]
    mock_repo.resolve_transaction_reference_availability.return_value = (
        TransactionReferenceAvailability(
            portfolio_exists=True,
            instrument_exists=False,
            cash_account_exists=None,
        )
    )

    await transaction_consumer.handle_persistence(AsyncMock(), valid_transaction_event)

    mock_repo.create_or_update_transaction.assert_awaited_once_with(valid_transaction_event)
    assert "Transaction raw landing has unresolved instrument reference." in caplog.text
    warning = next(
        record
        for record in caplog.records
        if record.message == "Transaction raw landing has unresolved instrument reference."
    )
    assert warning.reason_code == "transaction_instrument_reference_pending"
    assert warning.policy_id == "raw_transaction_instrument_reference_policy_v1"
    assert warning.downstream_lifecycle_blocked is True


async def test_handle_persistence_allows_provisional_raw_landing_for_missing_cash_account(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
    mock_dependencies: dict,
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.WARNING, logger=TRANSACTION_CONSUMER_LOGGER)
    mock_repo = mock_dependencies["repo"]
    event = valid_transaction_event.model_copy(
        update={
            "settlement_cash_account_id": " CASH-ACC-404 ",
            "settlement_cash_instrument_id": " CASH_USD ",
        }
    )
    mock_repo.resolve_transaction_reference_availability.return_value = (
        TransactionReferenceAvailability(
            portfolio_exists=True,
            instrument_exists=True,
            cash_account_exists=False,
        )
    )

    await transaction_consumer.handle_persistence(AsyncMock(), event)

    mock_repo.resolve_transaction_reference_availability.assert_awaited_once_with(
        portfolio_id="PORT_UT_01",
        tenant_id="tenant-test",
        security_id="SEC_UT_01",
        cash_account_id=" CASH-ACC-404 ",
        cash_security_id=" CASH_USD ",
        as_of_date=event.transaction_date.date(),
    )
    mock_repo.create_or_update_transaction.assert_awaited_once_with(event)
    assert (
        "Transaction raw landing has unresolved settlement cash-account reference." in caplog.text
    )
    warning = next(
        record
        for record in caplog.records
        if record.message
        == "Transaction raw landing has unresolved settlement cash-account reference."
    )
    assert warning.reason_code == "transaction_cash_account_reference_pending"
    assert warning.policy_id == "raw_transaction_cash_account_reference_policy_v1"
    assert warning.downstream_lifecycle_blocked is True
