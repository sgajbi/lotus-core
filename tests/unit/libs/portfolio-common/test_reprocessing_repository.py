# tests/unit/libs/portfolio-common/test_reprocessing_repository.py
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.config import KAFKA_TRANSACTIONS_PERSISTED_TOPIC
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.transaction import transaction_payload_fingerprint
from portfolio_common.events import TransactionEvent
from portfolio_common.ingestion_lineage import ingestion_job_id_var
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.reprocessing_repository import (
    ReprocessingReplayError,
    ReprocessingRepository,
    load_transaction_fee_facts,
    load_transaction_fee_receipts,
    load_transaction_replay_rows,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class FakeReplayReader:
    def __init__(self, transactions: list[SimpleNamespace]) -> None:
        self.transactions = transactions
        self.requested_ids: list[str] | None = None

    async def list_transactions_to_replay(
        self,
        ordered_transaction_ids: list[str],
    ) -> list[SimpleNamespace]:
        self.requested_ids = ordered_transaction_ids
        return self.transactions


class FakeReplayPublisher:
    def __init__(self) -> None:
        self.messages = []

    def publish_replay_message(self, message) -> None:
        self.messages.append(message)

    def confirm_replay_delivery(self) -> int:
        return 0


def _replay_transaction(transaction_id: str, portfolio_id: str = "P1") -> SimpleNamespace:
    return SimpleNamespace(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        tenant_id="tenant-test",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime.now(UTC),
        transaction_type="BUY",
        quantity=10,
        price=100,
        gross_transaction_amount=1000,
        currency="USD",
        trade_currency="USD",
        trade_fee=Decimal("0.0"),
    )


def _tenant_owned_rows(transactions: list[DBTransaction]) -> list[dict[str, object]]:
    return [
        {
            **{
                column.name: getattr(transaction, column.name)
                for column in DBTransaction.__table__.columns
                if column.name in TransactionEvent.model_fields
            },
            "tenant_id": "tenant-test",
            "payload_fingerprint": transaction_payload_fingerprint(
                TransactionEvent.model_validate(
                    {
                        column.name: getattr(transaction, column.name)
                        for column in DBTransaction.__table__.columns
                        if column.name in TransactionEvent.model_fields
                    }
                ).model_dump(mode="python")
            ),
        }
        for transaction in transactions
    ]


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)

    async def execute(statement):
        if "transaction_costs" in str(statement) or "outbox_events" in str(statement):
            empty = MagicMock()
            empty.mappings.return_value.all.return_value = []
            return empty
        return session.execute.return_value

    session.execute.side_effect = execute
    return session


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    mock = MagicMock(spec=KafkaProducer)
    mock.flush.return_value = 0
    return mock


@pytest.fixture
def repository(
    mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
) -> ReprocessingRepository:
    """Provides an instance of the ReprocessingRepository with mock dependencies."""
    return ReprocessingRepository(db=mock_db_session, kafka_producer=mock_kafka_producer)


async def test_reprocess_transactions_by_ids_success(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    """
    GIVEN a list of valid transaction IDs that exist in the database
    WHEN reprocess_transactions_by_ids is called
    THEN it should fetch the transactions and republish them to the correct Kafka topic.
    """
    # ARRANGE
    mock_transactions = [
        DBTransaction(
            transaction_id="TXN1",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),  # FIX: Provide a valid default value
        )
    ]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = _tenant_owned_rows(mock_transactions)
    mock_db_session.execute.return_value = mock_result

    # ACT
    count = await repository.reprocess_transactions_by_ids(transaction_ids=["TXN1"])

    # ASSERT
    assert count == 1
    assert mock_db_session.execute.await_count == 1

    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs

    assert call_args["topic"] == KAFKA_TRANSACTIONS_PERSISTED_TOPIC
    assert call_args["key"] == "P1|S1"
    assert call_args["value"]["transaction_id"] == "TXN1"

    mock_kafka_producer.flush.assert_called_once()


async def test_reprocess_no_transactions_found(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    """
    GIVEN a list of transaction IDs that do not exist in the database
    WHEN reprocess_transactions_by_ids is called
    THEN it should not publish any messages and return 0.
    """
    # ARRANGE
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []  # No transactions found
    mock_db_session.execute.return_value = mock_result

    # ACT
    count = await repository.reprocess_transactions_by_ids(transaction_ids=["TXN_NOT_FOUND"])

    # ASSERT
    assert count == 0
    mock_db_session.execute.assert_awaited_once()
    mock_kafka_producer.publish_message.assert_not_called()


async def test_reprocess_transactions_preserves_requested_input_order(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    """
    GIVEN multiple matching transactions
    WHEN reprocess_transactions_by_ids is called
    THEN the repository should republish them in the same deterministic order
    requested by the caller.
    """
    mock_transactions = [
        DBTransaction(
            transaction_id="TXN_B",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
        DBTransaction(
            transaction_id="TXN_A",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
    ]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = _tenant_owned_rows(mock_transactions)
    mock_db_session.execute.return_value = mock_result

    count = await repository.reprocess_transactions_by_ids(transaction_ids=["TXN_B", "TXN_A"])

    assert count == 2
    published_ids = [
        call.kwargs["value"]["transaction_id"]
        for call in mock_kafka_producer.publish_message.call_args_list
    ]
    assert published_ids == ["TXN_B", "TXN_A"]


async def test_reprocess_transactions_deduplicates_requested_ids(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    """
    GIVEN duplicate transaction IDs in the caller request
    WHEN reprocess_transactions_by_ids is called
    THEN each canonical transaction should be republished only once, preserving first-seen order.
    """
    mock_transactions = [
        DBTransaction(
            transaction_id="TXN_B",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
        DBTransaction(
            transaction_id="TXN_A",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
    ]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = _tenant_owned_rows(mock_transactions)
    mock_db_session.execute.return_value = mock_result

    count = await repository.reprocess_transactions_by_ids(
        transaction_ids=["TXN_B", "TXN_A", "TXN_B", "TXN_A"]
    )

    assert count == 2
    published_ids = [
        call.kwargs["value"]["transaction_id"]
        for call in mock_kafka_producer.publish_message.call_args_list
    ]
    assert published_ids == ["TXN_B", "TXN_A"]


async def test_reprocess_transactions_omits_not_set_correlation_header(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    mock_transactions = [
        DBTransaction(
            transaction_id="TXN1",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        )
    ]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = _tenant_owned_rows(mock_transactions)
    mock_db_session.execute.return_value = mock_result

    token = correlation_id_var.set("<not-set>")
    try:
        count = await repository.reprocess_transactions_by_ids(transaction_ids=["TXN1"])
    finally:
        correlation_id_var.reset(token)

    assert count == 1
    assert mock_kafka_producer.publish_message.call_args.kwargs["headers"] == [
        ("lotus-transaction-processing-intent", b"repair")
    ]


async def test_reprocess_transactions_reports_remaining_ids_on_partial_publish_failure(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    mock_transactions = [
        DBTransaction(
            transaction_id="TXN_A",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
        DBTransaction(
            transaction_id="TXN_B",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
        DBTransaction(
            transaction_id="TXN_C",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
    ]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = _tenant_owned_rows(mock_transactions)
    mock_db_session.execute.return_value = mock_result
    mock_kafka_producer.publish_message.side_effect = [None, RuntimeError("broker timeout")]

    with pytest.raises(ReprocessingReplayError) as exc_info:
        await repository.reprocess_transactions_by_ids(["TXN_A", "TXN_B", "TXN_C"])

    assert exc_info.value.failed_transaction_ids == ["TXN_B", "TXN_C"]
    assert exc_info.value.published_record_count == 1
    assert "Remaining transaction ids: TXN_B, TXN_C." in str(exc_info.value)


async def test_reprocess_transactions_fails_on_flush_timeout(
    repository: ReprocessingRepository, mock_db_session: AsyncMock, mock_kafka_producer: MagicMock
):
    mock_transactions = [
        DBTransaction(
            transaction_id="TXN_A",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
        DBTransaction(
            transaction_id="TXN_B",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime.now(UTC),
            transaction_type="BUY",
            quantity=10,
            price=100,
            gross_transaction_amount=1000,
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0.0"),
        ),
    ]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = _tenant_owned_rows(mock_transactions)
    mock_db_session.execute.return_value = mock_result
    mock_kafka_producer.flush.return_value = 1

    with pytest.raises(ReprocessingReplayError) as exc_info:
        await repository.reprocess_transactions_by_ids(["TXN_A", "TXN_B"])

    assert exc_info.value.failed_transaction_ids == ["TXN_A", "TXN_B"]
    assert "Delivery confirmation timed out while republishing transactions." in str(exc_info.value)


async def test_reprocess_transactions_can_run_through_reader_and_publisher_ports():
    reader = FakeReplayReader([_replay_transaction("TXN_A", portfolio_id="PORT-1")])
    publisher = FakeReplayPublisher()
    repository = ReprocessingRepository.from_ports(reader=reader, publisher=publisher)

    count = await repository.reprocess_transactions_by_ids(
        ["TXN_A", "TXN_A"],
        correlation_id=" corr-explicit ",
        repair_delivery_id=" repair-command-001 ",
    )

    assert count == 1
    assert reader.requested_ids == ["TXN_A"]
    assert publisher.messages[0].payload["transaction_id"] == "TXN_A"
    assert publisher.messages[0].headers == [
        ("correlation_id", b"corr-explicit"),
        ("lotus-transaction-repair-delivery-id", b"repair-command-001"),
        ("lotus-transaction-processing-intent", b"repair"),
    ]


async def test_reprocess_transactions_propagates_context_ingestion_job_owner():
    reader = FakeReplayReader([_replay_transaction("TXN_A", portfolio_id="PORT-1")])
    publisher = FakeReplayPublisher()
    repository = ReprocessingRepository.from_ports(reader=reader, publisher=publisher)

    token = ingestion_job_id_var.set(" job-replay-001 ")
    try:
        count = await repository.reprocess_transactions_by_ids(
            ["TXN_A"],
            correlation_id="corr-replay-001",
        )
    finally:
        ingestion_job_id_var.reset(token)

    assert count == 1
    assert publisher.messages[0].headers == [
        ("correlation_id", b"corr-replay-001"),
        ("ingestion_job_id", b"job-replay-001"),
        ("lotus-transaction-processing-intent", b"repair"),
    ]


def _mapping_result(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _postgresql_statement(statement):
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(compiled).split())


async def test_replay_source_capture_locks_original_owners_before_roots_and_preserves_order():
    observed = [
        {"transaction_id": "TXN_B", "portfolio_id": "P2", "quantity": 2},
        {"transaction_id": "TXN_A", "portfolio_id": "P1", "quantity": 1},
    ]
    locked = [observed[1] | {"quantity": 10}, observed[0] | {"quantity": 20}]
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [
        _mapping_result(observed),
        MagicMock(),
        _mapping_result(locked),
    ]

    captured = await load_transaction_replay_rows(session, ["TXN_B", "TXN_A"], lock_sources=True)

    assert captured == [locked[1], locked[0]]
    assert captured[0] is locked[1] and captured[1] is locked[0]
    assert session.execute.await_count == 3
    initial, portfolios, roots = [
        _postgresql_statement(call.args[0]) for call in session.execute.await_args_list
    ]
    assert "transactions.transaction_id IN ('TXN_B', 'TXN_A')" in initial
    assert "JOIN portfolios ON portfolios.portfolio_id = transactions.portfolio_id" in initial
    assert "ORDER BY CASE transactions.transaction_id" in initial
    assert "FOR UPDATE" not in initial
    assert "portfolios.portfolio_id IN ('P1', 'P2')" in portfolios
    assert "ORDER BY portfolios.portfolio_id FOR UPDATE OF portfolios" in portfolios
    assert "transactions.transaction_id IN ('TXN_B', 'TXN_A')" in roots
    assert "transactions.portfolio_id IN ('P1', 'P2')" in roots
    assert "ORDER BY transactions.transaction_id FOR UPDATE OF transactions" in roots
    assert "ORDER BY CASE" not in roots


@pytest.mark.parametrize("change", ["portfolio", "missing", "extra"])
async def test_replay_source_capture_refuses_changed_locked_root_membership(change):
    observed = [
        {"transaction_id": "TXN_B", "portfolio_id": "P2"},
        {"transaction_id": "TXN_A", "portfolio_id": "P1"},
    ]
    locked = [dict(row) for row in observed]
    if change == "portfolio":
        locked[0]["portfolio_id"] = "FOREIGN"
    elif change == "missing":
        locked.pop()
    else:
        locked.append({"transaction_id": "EXTRA", "portfolio_id": "P1"})
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [
        _mapping_result(observed),
        MagicMock(),
        _mapping_result(locked),
    ]

    with pytest.raises(ValueError, match="^Canonical replay root changed during source capture$"):
        await load_transaction_replay_rows(session, ["TXN_B", "TXN_A"], lock_sources=True)

    assert session.execute.await_count == 3
    portfolios, roots = [
        _postgresql_statement(call.args[0]) for call in session.execute.await_args_list[1:]
    ]
    assert "portfolios.portfolio_id IN ('P1', 'P2')" in portfolios
    assert "transactions.portfolio_id IN ('P1', 'P2')" in roots
    assert "transactions.transaction_id IN ('TXN_B', 'TXN_A')" in roots
    assert "FOREIGN" not in portfolios + roots and "EXTRA" not in portfolios + roots


@pytest.mark.parametrize("lock_sources,has_rows", [(True, False), (False, True), (False, False)])
async def test_replay_source_capture_empty_or_unlocked_returns_without_locking(
    lock_sources, has_rows
):
    observed = [{"transaction_id": "TXN_A", "portfolio_id": "P1"}] if has_rows else []
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _mapping_result(observed)

    assert (
        await load_transaction_replay_rows(session, ["TXN_A"], lock_sources=lock_sources)
        == observed
    )

    session.execute.assert_awaited_once()
    assert "FOR UPDATE" not in _postgresql_statement(session.execute.call_args.args[0])


async def test_empty_public_replay_does_not_read_or_publish():
    reader = FakeReplayReader([_replay_transaction("TXN_A")])
    publisher = MagicMock(spec=FakeReplayPublisher)
    repository = ReprocessingRepository.from_ports(reader=reader, publisher=publisher)

    assert await repository.reprocess_transactions_by_ids([]) == 0

    assert reader.requested_ids is None
    publisher.publish_replay_message.assert_not_called()
    publisher.confirm_replay_delivery.assert_not_called()


async def test_empty_fee_fact_batch_does_not_query_even_with_locked_receipt_scope():
    session = AsyncMock(spec=AsyncSession)

    assert await load_transaction_fee_facts(
        session,
        [],
        lock_sources=True,
        receipt_scopes=[("TENANT", "SERVICE", "P1", "KEY")],
    ) == ([], [], [])

    session.execute.assert_not_awaited()


@pytest.mark.parametrize("lock_sources", [False, True])
async def test_receipt_only_lookup_preserves_exact_query_without_cost_or_raw_reads(lock_sources):
    scopes = [("TENANT", "SERVICE", "P1", "KEY"), ("TENANT_B", "SERVICE", "P2", "KEY_B")]
    receipts = [{"semantic_key": "KEY", "payload_fingerprint": "HASH"}]
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _mapping_result(receipts)
    assert await load_transaction_fee_receipts(session, [], lock_sources=lock_sources) == []
    session.execute.assert_not_awaited()
    assert (
        await load_transaction_fee_receipts(session, scopes, lock_sources=lock_sources) == receipts
    )
    session.execute.assert_awaited_once()
    statement = _postgresql_statement(session.execute.await_args.args[0])
    assert "transaction_costs" not in statement and "outbox_events" not in statement
    for tenant, service, portfolio, key in scopes:
        for column, value in zip(
            ("tenant_id", "service_name", "portfolio_id", "semantic_key"),
            (tenant, service, portfolio, key),
            strict=True,
        ):
            assert f"processed_events.{column} = '{value}'" in statement
    assert " OR " in statement and "ORDER BY processed_events.id" in statement
    assert ("FOR SHARE OF processed_events" in statement) == lock_sources


@pytest.mark.parametrize("lock_sources", [False, True])
async def test_fee_fact_queries_preserve_bounded_scope_order_and_requested_read_locks(lock_sources):
    rows = [{"transaction_id": "TXN_B", "portfolio_id": "P1"}]
    facts = (
        [{"transaction_id": "TXN_B", "fee_type": "brokerage", "amount": Decimal(1)}],
        [{"aggregate_id": "P1", "payload": {"transaction_id": "TXN_B"}}],
        [{"tenant_id": "TENANT", "semantic_key": "KEY", "payload_fingerprint": "HASH"}],
    )
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [_mapping_result(family) for family in facts]

    assert (
        await load_transaction_fee_facts(
            session,
            rows,
            lock_sources=lock_sources,
            receipt_scopes=[("TENANT", "SERVICE", "P1", "KEY")],
        )
        == facts
    )

    assert session.execute.await_count == 3
    fees, raw, receipts = [
        _postgresql_statement(call.args[0]) for call in session.execute.await_args_list
    ]
    assert "transaction_costs.transaction_id IN ('TXN_B')" in fees
    assert "ORDER BY transaction_costs.transaction_id, transaction_costs.id" in fees
    assert "outbox_events.aggregate_type = 'RawTransaction'" in raw
    assert "outbox_events.event_type = 'RawTransactionPersisted'" in raw
    assert "outbox_events.aggregate_id IN ('P1')" in raw
    assert "->> 'transaction_id'" in raw and "IN ('TXN_B')" in raw
    assert "ORDER BY outbox_events.id" in raw
    assert "processed_events.tenant_id = 'TENANT'" in receipts
    assert "processed_events.service_name = 'SERVICE'" in receipts
    assert "processed_events.portfolio_id = 'P1'" in receipts
    assert "processed_events.semantic_key = 'KEY'" in receipts
    assert "ORDER BY processed_events.id" in receipts
    for statement, table in [
        (fees, "transaction_costs"),
        (raw, "outbox_events"),
        (receipts, "processed_events"),
    ]:
        if lock_sources:
            assert f"FOR SHARE OF {table}" in statement
        else:
            assert "FOR SHARE" not in statement and "FOR UPDATE" not in statement


@pytest.mark.parametrize("lock_sources", [False, True])
async def test_raw_source_fixed_literals_leave_requested_identifiers_bound(lock_sources):
    transaction_id = "TXN'); DROP TABLE outbox_events; --"
    portfolio_id = "PORT' OR TRUE --"
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [_mapping_result([]), _mapping_result([])]

    assert await load_transaction_fee_facts(
        session,
        [{"transaction_id": transaction_id, "portfolio_id": portfolio_id}],
        lock_sources=lock_sources,
    ) == ([], [], [])

    statement = session.execute.await_args_list[1].args[0]
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True}
    )
    sql = str(compiled)
    assert "aggregate_type = 'RawTransaction'" in sql
    assert "event_type = 'RawTransactionPersisted'" in sql
    assert "CAST((outbox_events.payload ->> 'transaction_id') AS VARCHAR)" in sql
    assert set(compiled.params.values()) == {portfolio_id, transaction_id}
    assert transaction_id not in sql and portfolio_id not in sql
    assert "ORDER BY outbox_events.id" in sql
    assert "LIMIT" not in sql and "DISTINCT" not in sql
    assert ("FOR SHARE OF outbox_events" in sql) == lock_sources
