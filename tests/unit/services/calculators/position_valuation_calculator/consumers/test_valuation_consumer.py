# tests/unit/services/calculators/position-valuation-calculator/consumers/test_valuation_consumer.py
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    MarketPrice,
    Portfolio,
    PositionHistory,
)
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    InstrumentValuationPolicyAssignment,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    MarketPriceSourceFactStatus,
    MissingValuationPolicyAssignmentError,
    PositionValuationEvidence,
    ValuationAuthorityScope,
    ValuationPolicyAssignmentStatus,
    canonical_content_hash,
    resolve_position_valuation_policy,
    resolve_valuation_policy_assignment,
)
from portfolio_common.events import (
    PortfolioValuationRequiredEvent,
)
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.valuation_job_contracts import (
    VALUATION_CLAIM_HEADER,
    ValuationJobTransitionOutcome,
)
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_valuation_calculator.app.consumers.valuation_consumer import (  # noqa: E501
    ValuationConsumer,
    _valuation_claim_token,
)
from src.services.calculators.position_valuation_calculator.app.ports import (
    ResolvedRuntimeValuationPolicy,
)
from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)
from src.services.calculators.position_valuation_calculator.app.valuation_processor import (
    ValuationJobProcessor,
    ValuationProcessorDependencies,
    ValuationReferenceData,
)
from tests.unit.test_support.async_session_iter import make_single_session_getter

pytestmark = pytest.mark.asyncio


@pytest.fixture
def consumer(mock_dependencies: dict) -> ValuationConsumer:
    """Provides a clean instance of the ValuationConsumer."""
    consumer = ValuationConsumer(
        bootstrap_servers="mock_server",
        topic="valuation.job.requested",
        group_id="test_group",
        valuation_processor=mock_dependencies["processor"],
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer


@pytest.fixture
def mock_event() -> PortfolioValuationRequiredEvent:
    """Provides a consistent valuation event for tests."""
    return PortfolioValuationRequiredEvent(
        portfolio_id="PORT_VAL_01",
        security_id="SEC_VAL_01",
        valuation_date=date(2025, 8, 1),
        epoch=1,
    )


@pytest.fixture
def mock_kafka_message(mock_event: PortfolioValuationRequiredEvent) -> MagicMock:
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    mock_msg.key.return_value = mock_event.portfolio_id.encode("utf-8")
    mock_msg.topic.return_value = "valuation.job.requested"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = [
        ("correlation_id", b"test-corr-id-123"),
        (VALUATION_CLAIM_HEADER, b"a" * 32),
    ]
    return mock_msg


@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)
    mock_valuation_repo = AsyncMock(spec=ValuationRepository)
    mock_valuation_repo.update_job_status.return_value = (
        ValuationJobTransitionOutcome.TERMINAL_APPLIED
    )

    mock_db_session = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def mock_begin_transaction():
        yield

    mock_db_session.begin.side_effect = mock_begin_transaction

    get_session_gen = make_single_session_getter(mock_db_session)

    market_price_source_fact_resolver = AsyncMock()
    valuation_policy_assignment_resolver = AsyncMock()
    valuation_receipt_repo = AsyncMock()
    source_evidence_builder = MagicMock()
    dependency_factory = MagicMock()
    dependency_factory.from_session.return_value = ValuationProcessorDependencies(
        repo=mock_valuation_repo,
        idempotency_repo=mock_idempotency_repo,
        outbox_repo=mock_outbox_repo,
        market_price_source_fact_resolver=market_price_source_fact_resolver,
        valuation_policy_assignment_resolver=valuation_policy_assignment_resolver,
        valuation_receipt_repo=valuation_receipt_repo,
        source_evidence_builder=source_evidence_builder,
    )
    processor = ValuationJobProcessor(
        session_provider=get_session_gen,
        dependency_factory=dependency_factory,
    )
    yield {
        "idempotency_repo": mock_idempotency_repo,
        "outbox_repo": mock_outbox_repo,
        "valuation_repo": mock_valuation_repo,
        "dependency_factory": dependency_factory,
        "market_price_source_fact_resolver": market_price_source_fact_resolver,
        "processor": processor,
        "source_evidence_builder": source_evidence_builder,
        "valuation_policy_assignment_resolver": valuation_policy_assignment_resolver,
        "valuation_receipt_repo": valuation_receipt_repo,
    }


def _source_reference(record_id: str) -> FinancialSourceReference:
    return FinancialSourceReference(
        source_system="valuation-worker-test",
        source_record_id=record_id,
        source_revision="1",
        source_content_hash=canonical_content_hash({"record_id": record_id}),
        observed_at=datetime(2025, 8, 1, 8, tzinfo=UTC),
    )


async def test_invalid_valuation_event_is_raised_to_shared_recovery_boundary(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
) -> None:
    mock_kafka_message.value.return_value = b'{"portfolio_id":"PORT_INVALID"}'

    with pytest.raises(ValidationError):
        await consumer.process_message(mock_kafka_message)

    consumer._send_to_dlq_async.assert_not_awaited()


async def test_valuation_processor_executes_success_path_without_kafka_consumer(
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_idempotency_repo.claim_event_processing.return_value = True
    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency="USD",
        security_id=mock_event.security_id,
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("90"),
        currency="USD",
        price_date=mock_event.valuation_date,
    )
    persisted_snapshot = DailyPositionSnapshot(
        id=7,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.valuation_date,
        epoch=mock_event.epoch,
        market_value_local=Decimal("9000"),
        valuation_status="VALUED_CURRENT",
    )
    mock_valuation_repo.upsert_daily_snapshot.return_value = persisted_snapshot

    with patch(
        "src.services.calculators.position_valuation_calculator.app."
        "valuation_processor.VALUATION_QUOTE_AUTHORITY_PATH_TOTAL"
    ) as authority_path_metric:
        await mock_dependencies["processor"].process_valid_event(
            mock_event,
            "valuation.job.requested-0-91",
            "processor-corr-id",
            claim_token="a" * 32,
        )

    mock_idempotency_repo.claim_event_processing.assert_awaited_once_with(
        "valuation.job.requested-0-91",
        mock_event.portfolio_id,
        "position-valuation-calculator",
        "processor-corr-id",
    )
    mock_valuation_repo.update_job_status.assert_awaited_once()
    assert (
        mock_valuation_repo.update_job_status.await_args.kwargs["expected_claim_token"] == "a" * 32
    )
    mock_outbox_repo.create_outbox_event.assert_awaited_once()
    assert mock_outbox_repo.create_outbox_event.call_args.kwargs["partition_key"].value == (
        f"{mock_event.portfolio_id}|{mock_event.security_id}"
    )
    assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
        "processor-corr-id"
    )
    mock_dependencies["valuation_policy_assignment_resolver"].resolve_many.assert_not_awaited()
    mock_dependencies["market_price_source_fact_resolver"].resolve_many.assert_not_awaited()
    mock_dependencies["valuation_receipt_repo"].upsert.assert_awaited_once()
    authority_path_metric.labels.assert_called_once_with("legacy", "unscoped_portfolio")


async def test_unscoped_bond_fails_without_publishing_a_valued_snapshot(
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
) -> None:
    repo = mock_dependencies["valuation_repo"]
    mock_dependencies["idempotency_repo"].claim_event_processing.return_value = True
    repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("10"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )
    repo.get_instrument.return_value = Instrument(
        currency="USD",
        security_id=mock_event.security_id,
        product_type="BOND",
    )
    repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
    )
    repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("99.25"),
        currency="USD",
        price_date=mock_event.valuation_date,
    )

    def _persist(snapshot: DailyPositionSnapshot) -> DailyPositionSnapshot:
        snapshot.id = 8
        return snapshot

    repo.upsert_daily_snapshot.side_effect = _persist

    with patch(
        "src.services.calculators.position_valuation_calculator.app."
        "valuation_processor.VALUATION_JOBS_FAILED_TOTAL"
    ) as failed_metric:
        await mock_dependencies["processor"].process_valid_event(
            mock_event,
            "valuation.job.requested-0-92",
            "processor-corr-id",
            claim_token="a" * 32,
        )

    persisted_snapshot = repo.upsert_daily_snapshot.await_args.args[0]
    assert persisted_snapshot.valuation_status == "FAILED"
    assert persisted_snapshot.market_value is None
    assert persisted_snapshot.market_value_local is None
    assert repo.update_job_status.await_args.kwargs["failure_reason"] == (
        "bond valuation requires explicit quote-convention authority"
    )
    failed_metric.labels.assert_called_once_with(reason="missing_bond_quote_authority")
    mock_dependencies["valuation_receipt_repo"].upsert.assert_not_awaited()
    mock_dependencies["valuation_receipt_repo"].delete.assert_awaited_once_with(snapshot_id=8)


@pytest.mark.parametrize(
    ("cost_basis", "cost_basis_local"),
    [(Decimal("1"), Decimal("0")), (Decimal("0"), Decimal("1"))],
)
async def test_zero_quantity_bond_with_residual_cost_fails_without_quote_authority(
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
    cost_basis: Decimal,
    cost_basis_local: Decimal,
) -> None:
    repo = mock_dependencies["valuation_repo"]
    mock_dependencies["idempotency_repo"].claim_event_processing.return_value = True
    repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("0"),
        cost_basis=cost_basis,
        cost_basis_local=cost_basis_local,
    )
    repo.get_instrument.return_value = Instrument(
        currency="USD",
        security_id=mock_event.security_id,
        product_type="BOND",
    )
    repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
    )
    repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("99.25"),
        currency="USD",
        price_date=mock_event.valuation_date,
    )

    def _persist(snapshot: DailyPositionSnapshot) -> DailyPositionSnapshot:
        snapshot.id = 96
        return snapshot

    repo.upsert_daily_snapshot.side_effect = _persist

    with patch(
        "src.services.calculators.position_valuation_calculator.app."
        "valuation_processor.VALUATION_JOBS_FAILED_TOTAL"
    ) as failed_metric:
        await mock_dependencies["processor"].process_valid_event(
            mock_event,
            "valuation.job.requested-0-96",
            "processor-corr-id",
            claim_token="a" * 32,
        )

    persisted_snapshot = repo.upsert_daily_snapshot.await_args.args[0]
    assert persisted_snapshot.valuation_status == "FAILED"
    assert repo.update_job_status.await_args.kwargs["failure_reason"] == (
        "bond valuation requires explicit quote-convention authority"
    )
    failed_metric.labels.assert_called_once_with(reason="missing_bond_quote_authority")
    mock_dependencies["valuation_receipt_repo"].upsert.assert_not_awaited()


@pytest.mark.parametrize(
    "headers",
    [
        [(VALUATION_CLAIM_HEADER, b"not-a-token")],
        [
            (VALUATION_CLAIM_HEADER, b"a" * 32),
            (VALUATION_CLAIM_HEADER, b"b" * 32),
        ],
    ],
)
async def test_valuation_claim_token_rejects_malformed_or_duplicate_authority(headers) -> None:
    message = MagicMock()
    message.headers.return_value = headers

    with pytest.raises(ValueError):
        _valuation_claim_token(message)


async def test_valuation_claim_token_preserves_legacy_headerless_dispatch() -> None:
    message = MagicMock()
    message.headers.return_value = [("correlation_id", b"legacy")]

    assert _valuation_claim_token(message) is None


@pytest.mark.parametrize(
    (
        "policy_id",
        "quote_basis",
        "price",
        "quantity",
        "cost_basis",
        "expected_market_value",
        "expected_unrealized",
        "expected_status",
        "expects_receipt",
    ),
    [
        (
            "UNIT_PRICE_MARKET_VALUE",
            MarketPriceQuoteBasis.UNIT_PRICE,
            Decimal("1013.5"),
            Decimal("10"),
            Decimal("10000"),
            Decimal("10135.0000000000"),
            Decimal("135.0000000000"),
            "VALUED_CURRENT",
            True,
        ),
        (
            "DIRTY_PERCENT_FACE_MARKET_VALUE",
            MarketPriceQuoteBasis.PERCENT_OF_PRINCIPAL_DIRTY,
            Decimal("99.25"),
            Decimal("1000000"),
            Decimal("990000"),
            None,
            None,
            "FAILED",
            False,
        ),
    ],
)
async def test_scoped_portfolio_uses_exact_authority_without_legacy_price_read(
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
    policy_id: str,
    quote_basis: MarketPriceQuoteBasis,
    price: Decimal,
    quantity: Decimal,
    cost_basis: Decimal,
    expected_market_value: Decimal | None,
    expected_unrealized: Decimal | None,
    expected_status: str,
    expects_receipt: bool,
) -> None:
    repo = mock_dependencies["valuation_repo"]
    mock_dependencies["idempotency_repo"].claim_event_processing.return_value = True
    position = PositionHistory(
        quantity=quantity,
        cost_basis=cost_basis,
        cost_basis_local=cost_basis,
    )
    repo.get_last_position_history_before_date.return_value = position
    repo.get_instrument.return_value = Instrument(
        currency="USD",
        security_id=mock_event.security_id,
    )
    portfolio = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
        tenant_id="TENANT-SG",
        legal_book_id="BOOK-SG",
    )
    repo.get_portfolio.return_value = portfolio

    def _persist(snapshot: DailyPositionSnapshot) -> DailyPositionSnapshot:
        snapshot.id = 9
        return snapshot

    repo.upsert_daily_snapshot.side_effect = _persist

    price_fact = MarketPriceSourceFact(
        scope=ValuationAuthorityScope(
            "TENANT-SG",
            "BOOK-SG",
            mock_event.security_id,
        ),
        price_date=mock_event.valuation_date,
        price=price,
        currency="USD",
        quote_basis=quote_basis,
        source_reference=_source_reference("market-price"),
        fact_status=MarketPriceSourceFactStatus.ACTIVE,
        fact_version=1,
    )
    policy_assignment = resolve_valuation_policy_assignment(
        [
            InstrumentValuationPolicyAssignment(
                tenant_id="TENANT-SG",
                legal_book_id="BOOK-SG",
                security_id=mock_event.security_id,
                policy_id=policy_id,
                policy_version=1,
                valid_from=mock_event.valuation_date,
                valid_to=None,
                assignment_status=ValuationPolicyAssignmentStatus.ACTIVE,
                assignment_version=1,
                source_system="policy-master",
                source_record_id="assignment-1",
                source_revision="1",
                observed_at=datetime(2025, 8, 1, tzinfo=UTC),
                assignment_reason="explicit valuation representation",
            )
        ],
        tenant_id="TENANT-SG",
        legal_book_id="BOOK-SG",
        security_id=mock_event.security_id,
        valuation_date=mock_event.valuation_date,
    )
    policy = resolve_position_valuation_policy(policy_id, 1)
    policy_resolution = ResolvedRuntimeValuationPolicy(
        assignment=policy_assignment,
        policy=policy,
    )
    policy_resolver = mock_dependencies["valuation_policy_assignment_resolver"]
    price_resolver = mock_dependencies["market_price_source_fact_resolver"]
    policy_resolver.resolve_many.side_effect = lambda requests: {requests[0].key: policy_resolution}
    price_resolver.resolve_many.side_effect = lambda requests: {requests[0].key: price_fact}
    evidence = PositionValuationEvidence(
        policy_assignment=_source_reference("policy-assignment"),
        source_value=price_fact.source_reference,
        source_currency=price_fact.source_reference,
        reporting_currency=_source_reference("portfolio"),
        signed_quantity=_source_reference("position"),
    )
    mock_dependencies["source_evidence_builder"].return_value = evidence

    with patch(
        "src.services.calculators.position_valuation_calculator.app."
        "valuation_processor.VALUATION_QUOTE_AUTHORITY_PATH_TOTAL"
    ) as authority_path_metric:
        await mock_dependencies["processor"].process_valid_event(
            mock_event,
            "valuation.job.requested-0-95",
            "processor-corr-id",
        )

    repo.get_latest_price_for_position.assert_not_awaited()
    policy_resolver.resolve_many.assert_awaited_once()
    price_resolver.resolve_many.assert_awaited_once()
    mock_dependencies["source_evidence_builder"].assert_called_once_with(
        assignment=policy_assignment,
        price_fact=price_fact,
        position=position,
        portfolio=portfolio,
        fx_rate=None,
    )
    persisted_snapshot = repo.upsert_daily_snapshot.await_args.args[0]
    assert persisted_snapshot.market_price == (price if expects_receipt else None)
    assert persisted_snapshot.market_value_local == expected_market_value
    assert persisted_snapshot.unrealized_gain_loss_local == expected_unrealized
    assert persisted_snapshot.valuation_status == expected_status
    if expects_receipt:
        receipt = mock_dependencies["valuation_receipt_repo"].upsert.await_args.kwargs["receipt"]
        assert receipt.policy_id == policy_id
        assert receipt.receipt_hash
        mock_dependencies["valuation_receipt_repo"].delete.assert_not_awaited()
    else:
        mock_dependencies["valuation_receipt_repo"].upsert.assert_not_awaited()
        mock_dependencies["valuation_receipt_repo"].delete.assert_awaited_once_with(snapshot_id=9)
    authority_path_metric.labels.assert_called_once_with(
        "authoritative",
        "exact_portfolio_scope",
    )


async def test_scoped_portfolio_fails_closed_when_policy_authority_is_missing(
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
) -> None:
    repo = mock_dependencies["valuation_repo"]
    mock_dependencies["idempotency_repo"].claim_event_processing.return_value = True
    repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("10"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )
    repo.get_instrument.return_value = Instrument(
        currency="USD",
        security_id=mock_event.security_id,
    )
    repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
        tenant_id="TENANT-SG",
        legal_book_id="BOOK-SG",
    )
    policy_resolver = mock_dependencies["valuation_policy_assignment_resolver"]
    policy_resolver.resolve_many.side_effect = MissingValuationPolicyAssignmentError(
        "no exact authority"
    )

    repo.upsert_daily_snapshot.side_effect = lambda snapshot: DailyPositionSnapshot(
        id=77,
        portfolio_id=snapshot.portfolio_id,
        security_id=snapshot.security_id,
        date=snapshot.date,
        epoch=snapshot.epoch,
        quantity=snapshot.quantity,
        cost_basis=snapshot.cost_basis,
        cost_basis_local=snapshot.cost_basis_local,
        valuation_status=snapshot.valuation_status,
    )

    await mock_dependencies["processor"].process_valid_event(
        mock_event,
        "valuation.job.requested-0-96",
        "processor-corr-id",
    )

    repo.get_latest_price_for_position.assert_not_awaited()
    mock_dependencies["market_price_source_fact_resolver"].resolve_many.assert_not_awaited()
    repo.update_job_status.assert_awaited_once_with(
        mock_event.portfolio_id,
        mock_event.security_id,
        mock_event.valuation_date,
        mock_event.epoch,
        "FAILED",
        failure_reason="no exact authority",
        expected_claim_token=None,
    )
    failed_snapshot = repo.upsert_daily_snapshot.await_args.args[0]
    assert failed_snapshot.valuation_status == "FAILED"
    assert failed_snapshot.quantity == Decimal("10")
    assert failed_snapshot.cost_basis == Decimal("10000")
    assert failed_snapshot.market_price is None
    assert failed_snapshot.market_value is None
    assert failed_snapshot.market_value_local is None
    assert failed_snapshot.unrealized_gain_loss is None
    assert failed_snapshot.unrealized_gain_loss_local is None
    mock_dependencies["valuation_receipt_repo"].delete.assert_awaited_once_with(snapshot_id=77)
    mock_dependencies["valuation_receipt_repo"].upsert.assert_not_awaited()
    mock_dependencies["outbox_repo"].create_outbox_event.assert_awaited_once()


async def test_authoritative_valuation_persists_selected_fx_effective_date(
    mock_event: PortfolioValuationRequiredEvent,
) -> None:
    snapshot = DailyPositionSnapshot(
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.valuation_date,
        epoch=mock_event.epoch,
    )
    price_fact = MarketPriceSourceFact(
        scope=ValuationAuthorityScope("TENANT-SG", "BOOK-SG", mock_event.security_id),
        price_date=mock_event.valuation_date,
        price=Decimal("100"),
        currency="EUR",
        quote_basis=MarketPriceQuoteBasis.UNIT_PRICE,
        source_reference=_source_reference("market-price"),
        fact_status=MarketPriceSourceFactStatus.ACTIVE,
        fact_version=1,
    )
    valuation_result = MagicMock(
        market_value_reporting=Decimal("1100"),
        market_value_local=Decimal("1000"),
        unrealized_total_reporting=Decimal("200"),
        unrealized_total_local=Decimal("100"),
        unrealized_price_reporting=Decimal("110"),
        unrealized_fx_reporting=Decimal("90"),
    )
    selected_fx = FxRate(rate=Decimal("1.1"), rate_date=date(2025, 7, 31))

    ValuationJobProcessor._apply_authoritative_valuation_result(
        snapshot=snapshot,
        price_fact=price_fact,
        result=valuation_result,
        fx_rate=selected_fx,
    )

    assert snapshot.valuation_status == "VALUED_CURRENT"
    assert snapshot.valuation_fx_rate_date == date(2025, 7, 31)


async def test_valuation_processor_duplicate_claim_skips_valuation_reads(
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_idempotency_repo.claim_event_processing.return_value = False

    await mock_dependencies["processor"].process_valid_event(
        mock_event,
        "valuation.job.requested-0-92",
        "processor-corr-id",
    )

    mock_valuation_repo.get_last_position_history_before_date.assert_not_awaited()
    mock_valuation_repo.update_job_status.assert_not_awaited()
    mock_outbox_repo.create_outbox_event.assert_not_awaited()


@pytest.mark.parametrize(
    ("reference_data", "expected_message"),
    [
        (
            ValuationReferenceData(
                instrument=None,
                portfolio=Portfolio(portfolio_id="PORT_VAL_01"),
                price=None,
            ),
            "Instrument 'SEC_VAL_01' not found.",
        ),
        (
            ValuationReferenceData(
                instrument=Instrument(security_id="SEC_VAL_01"),
                portfolio=None,
                price=None,
            ),
            "Portfolio 'PORT_VAL_01' not found.",
        ),
    ],
)
async def test_missing_reference_data_message_names_the_unresolved_domain_record(
    mock_event: PortfolioValuationRequiredEvent,
    reference_data: ValuationReferenceData,
    expected_message: str,
) -> None:
    message = ValuationJobProcessor._missing_reference_data_message(
        mock_event,
        reference_data,
    )

    assert expected_message in message


async def test_valuation_processor_marks_snapshot_unvalued_when_price_is_missing(
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_idempotency_repo.claim_event_processing.return_value = True
    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency="USD",
        security_id=mock_event.security_id,
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = None

    def persist_snapshot(snapshot):
        snapshot.id = 93
        return snapshot

    mock_valuation_repo.upsert_daily_snapshot.side_effect = persist_snapshot

    await mock_dependencies["processor"].process_valid_event(
        mock_event,
        "valuation.job.requested-0-93",
        "processor-corr-id",
    )

    persisted_snapshot = mock_valuation_repo.upsert_daily_snapshot.call_args.args[0]
    assert persisted_snapshot.valuation_status == "UNVALUED"
    assert persisted_snapshot.market_value is None
    assert persisted_snapshot.market_value_local is None
    mock_valuation_repo.update_job_status.assert_awaited_once()
    mock_dependencies["valuation_receipt_repo"].delete.assert_awaited_once_with(snapshot_id=93)
    mock_dependencies["valuation_receipt_repo"].upsert.assert_not_awaited()
    mock_dependencies["outbox_repo"].create_outbox_event.assert_awaited_once()


@pytest.mark.parametrize(
    ("market_price", "instrument_currency", "portfolio_currency"),
    [
        (None, "USD", "USD"),
        (
            MarketPrice(
                price=Decimal("99"),
                currency="EUR",
                price_date=date(2025, 7, 31),
            ),
            "EUR",
            "USD",
        ),
    ],
)
async def test_valuation_processor_values_flat_position_without_quote_dependencies(
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
    market_price: MarketPrice | None,
    instrument_currency: str,
    portfolio_currency: str,
) -> None:
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_dependencies["idempotency_repo"].claim_event_processing.return_value = True
    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("0"),
        cost_basis=Decimal("0"),
        cost_basis_local=Decimal("0"),
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency=instrument_currency,
        security_id=mock_event.security_id,
        product_type="BOND",
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency=portfolio_currency,
        portfolio_id=mock_event.portfolio_id,
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = market_price

    def persist_snapshot(snapshot):
        snapshot.id = 94
        return snapshot

    mock_valuation_repo.upsert_daily_snapshot.side_effect = persist_snapshot

    await mock_dependencies["processor"].process_valid_event(
        mock_event,
        "valuation.job.requested-0-94",
        "processor-corr-id",
    )

    persisted_snapshot = mock_valuation_repo.upsert_daily_snapshot.call_args.args[0]
    assert persisted_snapshot.market_price is None
    assert persisted_snapshot.market_value == Decimal("0")
    assert persisted_snapshot.market_value_local == Decimal("0")
    assert persisted_snapshot.unrealized_gain_loss == Decimal("0")
    assert persisted_snapshot.unrealized_gain_loss_local == Decimal("0")
    assert persisted_snapshot.unrealized_price_gain_loss == Decimal("0")
    assert persisted_snapshot.unrealized_fx_gain_loss == Decimal("0")
    assert persisted_snapshot.valuation_status == "VALUED_CURRENT"
    receipt = mock_dependencies["valuation_receipt_repo"].upsert.await_args.kwargs["receipt"]
    assert receipt.snapshot_identity.security_id == mock_event.security_id
    assert receipt.supportability.value == "LEGACY_UNSCOPED"
    mock_valuation_repo.get_fx_rate.assert_not_awaited()
    mock_dependencies["valuation_receipt_repo"].delete.assert_not_awaited()
    mock_dependencies["outbox_repo"].create_outbox_event.assert_awaited_once()


async def test_valuation_processor_does_not_zero_value_residual_cost_without_price(
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
) -> None:
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_dependencies["idempotency_repo"].claim_event_processing.return_value = True
    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("0"),
        cost_basis=Decimal("1"),
        cost_basis_local=Decimal("1"),
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency="USD",
        security_id=mock_event.security_id,
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = None

    def persist_snapshot(snapshot):
        snapshot.id = 95
        return snapshot

    mock_valuation_repo.upsert_daily_snapshot.side_effect = persist_snapshot

    await mock_dependencies["processor"].process_valid_event(
        mock_event,
        "valuation.job.requested-0-95",
        "processor-corr-id",
    )

    persisted_snapshot = mock_valuation_repo.upsert_daily_snapshot.call_args.args[0]
    assert persisted_snapshot.valuation_status == "UNVALUED"
    assert persisted_snapshot.market_value is None
    assert persisted_snapshot.market_value_local is None
    mock_dependencies["valuation_receipt_repo"].delete.assert_awaited_once_with(snapshot_id=95)
    mock_dependencies["valuation_receipt_repo"].upsert.assert_not_awaited()


async def test_valuation_processor_marks_snapshot_stale_when_price_date_precedes_valuation_date(
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_idempotency_repo.claim_event_processing.return_value = True
    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency="USD",
        security_id=mock_event.security_id,
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("90"),
        currency="USD",
        price_date=date(2025, 7, 31),
    )

    def persist_snapshot(snapshot):
        snapshot.id = 94
        return snapshot

    mock_valuation_repo.upsert_daily_snapshot.side_effect = persist_snapshot

    await mock_dependencies["processor"].process_valid_event(
        mock_event,
        "valuation.job.requested-0-94",
        "processor-corr-id",
    )

    persisted_snapshot = mock_valuation_repo.upsert_daily_snapshot.call_args.args[0]
    assert persisted_snapshot.valuation_status == "VALUED_STALE"
    assert persisted_snapshot.market_value == Decimal("9000")
    assert persisted_snapshot.unrealized_gain_loss == Decimal("-1000")
    assert persisted_snapshot.unrealized_price_gain_loss == Decimal("-1000")
    assert persisted_snapshot.unrealized_fx_gain_loss == Decimal("0")
    assert persisted_snapshot.unrealized_gain_loss == (
        persisted_snapshot.unrealized_price_gain_loss + persisted_snapshot.unrealized_fx_gain_loss
    )
    mock_valuation_repo.update_job_status.assert_awaited_once()


async def test_valuation_consumer_success(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a valid valuation required event with an epoch
    WHEN the consumer processes the message
    THEN it should fetch position history for that epoch and create an
    epoch-tagged snapshot and event.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False

    mock_position_history = PositionHistory(
        quantity=Decimal("100"), cost_basis=Decimal("10000"), cost_basis_local=Decimal("8000")
    )
    mock_valuation_repo.get_last_position_history_before_date.return_value = mock_position_history

    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency="EUR", security_id=mock_event.security_id
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id=mock_event.portfolio_id
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("90"), currency="EUR", price_date=mock_event.valuation_date
    )
    mock_valuation_repo.get_fx_rate.return_value = FxRate(
        rate=Decimal("1.1"),
        rate_date=date(2025, 7, 31),
    )

    persisted_snapshot = DailyPositionSnapshot(
        id=1,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.valuation_date,
        epoch=mock_event.epoch,
        market_value_local=Decimal("9900"),
        valuation_status="VALUED_CURRENT",
    )
    mock_valuation_repo.upsert_daily_snapshot.return_value = persisted_snapshot

    token = correlation_id_var.set("<not-set>")
    try:
        # ACT
        await consumer.process_message(mock_kafka_message)
    finally:
        correlation_id_var.reset(token)

    # ASSERT
    mock_valuation_repo.get_last_position_history_before_date.assert_called_once_with(
        mock_event.portfolio_id, mock_event.security_id, mock_event.valuation_date, mock_event.epoch
    )
    valuation_candidate = mock_valuation_repo.upsert_daily_snapshot.call_args.args[0]
    assert valuation_candidate.valuation_fx_rate_date == date(2025, 7, 31)
    mock_outbox_repo.create_outbox_event.assert_called_once()

    payload = mock_outbox_repo.create_outbox_event.call_args.kwargs["payload"]
    assert payload["epoch"] == mock_event.epoch
    assert payload["id"] == persisted_snapshot.id
    assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
        "test-corr-id-123"
    )
    claimed_event_id = mock_idempotency_repo.claim_event_processing.call_args.args[0]
    assert claimed_event_id == "valuation.job.requested-0-1"
    assert mock_idempotency_repo.claim_event_processing.call_args.args[3] == "test-corr-id-123"


async def test_valuation_consumer_uses_kafka_delivery_identity_for_idempotency(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("8000"),
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(currency="USD")
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id="PORT_VAL_01",
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("90"),
        currency="USD",
        price_date=date(2025, 8, 1),
    )
    mock_valuation_repo.upsert_daily_snapshot.return_value = DailyPositionSnapshot(
        id=1,
        portfolio_id="PORT_VAL_01",
        security_id="SEC_VAL_01",
        date=date(2025, 8, 1),
        epoch=1,
    )

    await consumer.process_message(mock_kafka_message)

    claimed_event_id = mock_idempotency_repo.claim_event_processing.call_args.args[0]
    assert claimed_event_id == "valuation.job.requested-0-1"


async def test_valuation_consumer_normalizes_same_currency_without_fx_lookup(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency=" usd ",
        security_id=mock_event.security_id,
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency=" USD ",
        portfolio_id=mock_event.portfolio_id,
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("90"),
        currency=" usd ",
        price_date=mock_event.valuation_date,
    )
    mock_valuation_repo.upsert_daily_snapshot.return_value = DailyPositionSnapshot(
        id=1,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.valuation_date,
        epoch=mock_event.epoch,
        market_value_local=Decimal("9000"),
        valuation_status="VALUED_CURRENT",
    )

    await consumer.process_message(mock_kafka_message)

    mock_valuation_repo.get_fx_rate.assert_not_awaited()
    persisted_snapshot = mock_valuation_repo.upsert_daily_snapshot.call_args.args[0]
    assert persisted_snapshot.market_value == Decimal("9000")
    assert persisted_snapshot.market_value_local == Decimal("9000")
    assert persisted_snapshot.valuation_status == "VALUED_CURRENT"
    assert persisted_snapshot.valuation_fx_rate_date is None
    mock_outbox_repo.create_outbox_event.assert_called_once()


async def test_process_message_handles_data_not_found_error(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a job for which no position history exists
    WHEN the consumer processes the message
    THEN it should catch DataNotFoundError, mark the job as SKIPPED, and NOT send to DLQ.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False

    # Simulate the key error condition by having the repo return None
    mock_valuation_repo.get_last_position_history_before_date.return_value = None

    # ACT
    await consumer.process_message(mock_kafka_message)

    # ASSERT
    # Verify the job status was updated to the terminal 'SKIPPED' state
    mock_valuation_repo.update_job_status.assert_called_once()
    call_args = mock_valuation_repo.update_job_status.call_args.kwargs
    assert call_args["status"] == "SKIPPED_NO_POSITION"
    assert "Position history not found" in call_args["failure_reason"]

    # Verify other actions were NOT taken
    mock_outbox_repo.create_outbox_event.assert_not_called()
    consumer._send_to_dlq_async.assert_not_called()

    # Verify the event was still marked as processed to prevent retries
    mock_idempotency_repo.mark_event_processed.assert_called_once()


async def test_process_message_handles_unexpected_error(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a valid job that causes an unexpected error during valuation
    WHEN the consumer processes the message
    THEN it marks the job as FAILED and raises to the shared recovery boundary.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False

    # Mock all repo calls to succeed up to the point of failure
    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=1, cost_basis=1
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(currency="USD")
    mock_valuation_repo.get_portfolio.return_value = Portfolio(base_currency="USD")

    # ACT
    # Patch the logic layer to raise an unexpected error
    with patch(
        "src.services.calculators.position_valuation_calculator.app.valuation_processor.ValuationLogic.calculate_valuation_components",
        side_effect=ValueError("Unexpected logic error"),
    ) as mock_logic:
        with pytest.raises(ValueError, match="Unexpected logic error"):
            await consumer.process_message(mock_kafka_message)

    # ASSERT
    # Verify the logic was called, triggering the error
    mock_logic.assert_called_once()

    # Verify the job status was updated to FAILED
    mock_valuation_repo.update_job_status.assert_called_once()
    call_args = mock_valuation_repo.update_job_status.call_args.kwargs
    assert call_args["status"] == "FAILED"
    assert "Unexpected logic error" in call_args["failure_reason"]

    consumer._send_to_dlq_async.assert_not_awaited()

    # Verify no success event was published
    mock_outbox_repo.create_outbox_event.assert_not_called()

    # Idempotency key should NOT be marked as processed, as the message went to DLQ for retry
    mock_idempotency_repo.mark_event_processed.assert_not_called()


async def test_process_message_marks_job_failed_when_fx_rate_missing(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    """
    GIVEN valuation requires cross-currency conversion and FX is missing
    WHEN the consumer processes the message
    THEN it should persist a FAILED valuation snapshot and mark the job FAILED.
    """
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("8000"),
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency="EUR",
        security_id=mock_event.security_id,
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("90"),
        currency="EUR",
        price_date=mock_event.valuation_date,
    )
    mock_valuation_repo.get_fx_rate.return_value = None
    mock_valuation_repo.upsert_daily_snapshot.return_value = DailyPositionSnapshot(
        id=1,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.valuation_date,
        epoch=mock_event.epoch,
        valuation_status="FAILED",
    )

    await consumer.process_message(mock_kafka_message)

    mock_valuation_repo.update_job_status.assert_called_once()
    update_args = mock_valuation_repo.update_job_status.call_args.args
    update_kwargs = mock_valuation_repo.update_job_status.call_args.kwargs
    assert update_args[4] == "FAILED"
    assert "Missing FX rate" in update_kwargs["failure_reason"]
    mock_outbox_repo.create_outbox_event.assert_called_once()
    consumer._send_to_dlq_async.assert_not_called()
    assert mock_idempotency_repo.claim_event_processing.await_count == 1


@pytest.mark.parametrize(
    ("transition_outcome", "expected_reason"),
    [
        (ValuationJobTransitionOutcome.NOT_OWNED, "job ownership was lost"),
        (
            ValuationJobTransitionOutcome.REQUEUED,
            "newer source work requested requeue",
        ),
    ],
)
async def test_valuation_consumer_skips_success_side_effects_without_terminal_ownership(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
    transition_outcome: ValuationJobTransitionOutcome,
    expected_reason: str,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("8000"),
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency="EUR",
        security_id=mock_event.security_id,
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("90"),
        currency="EUR",
        price_date=mock_event.valuation_date,
    )
    mock_valuation_repo.get_fx_rate.return_value = FxRate(rate=Decimal("1.1"))
    mock_valuation_repo.update_job_status.return_value = transition_outcome

    with patch(
        "src.services.calculators.position_valuation_calculator.app.valuation_processor.logger.warning"
    ) as warning:
        await consumer.process_message(mock_kafka_message)

    mock_valuation_repo.update_job_status.assert_awaited_once()
    mock_valuation_repo.upsert_daily_snapshot.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_not_called()
    warning.assert_called_once()
    assert warning.call_args.args[2] == expected_reason
    assert warning.call_args.kwargs["extra"]["transition_outcome"] == transition_outcome.value
