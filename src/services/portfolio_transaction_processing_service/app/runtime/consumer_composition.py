from __future__ import annotations

from collections.abc import Callable

from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_CORPORATE_ACTION_MANIFEST_RECEIVED_TOPIC,
    KAFKA_FIXED_INCOME_BOOK_COST_AUTHORITY_RECEIVED_TOPIC,
    KAFKA_FIXED_INCOME_BOOK_COST_DISPOSAL_REPLAY_REQUESTED_TOPIC,
    KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
    KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
)
from portfolio_common.db import get_async_session_factory
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_consumer_execution import (
    KafkaConsumerExecutionProfile,
    load_kafka_consumer_execution_profile,
)

from ..application import (
    ProcessTransactionUseCase,
    ReplayBookedTransactionUseCase,
    RouteCorporateActionChildArrivalUseCase,
)
from ..application.corporate_action_manifest_ingestion import (
    HandleCorporateActionManifestEventUseCase,
)
from ..application.fixed_income_book_cost import (
    HandleFixedIncomeBookCostAuthorityEventUseCase,
)
from ..application.transaction_tenant_authority import TransactionTenantAuthorityPort
from ..delivery.kafka import (
    BookedTransactionReplayRequestConsumer,
    CorporateActionManifestConsumer,
    FixedIncomeBookCostAuthorityConsumer,
    FixedIncomeBookCostCorrectionReplayConsumer,
    TransactionProcessingConsumer,
)
from ..infrastructure.transaction_tenant_authority import SqlAlchemyTransactionTenantAuthority
from .dependency_composition import (
    build_corporate_action_child_arrival_use_case,
    build_corporate_action_manifest_use_case,
    build_fixed_income_book_cost_authority_use_case,
    build_process_transaction_use_case,
    build_replay_booked_transaction_use_case,
)

TRANSACTION_PROCESSING_CONSUMER_GROUP = "portfolio_transaction_processing_group"
TRANSACTION_REPLAY_REQUEST_CONSUMER_GROUP = "portfolio_transaction_replay_request_group"
FIXED_INCOME_BOOK_COST_AUTHORITY_CONSUMER_GROUP = "fixed_income_book_cost_authority_group"
FIXED_INCOME_BOOK_COST_CORRECTION_REPLAY_CONSUMER_GROUP = (
    "fixed_income_book_cost_correction_replay_group"
)
CORPORATE_ACTION_MANIFEST_CONSUMER_GROUP = "corporate_action_manifest_group"
# Source/reference events arrive on independent topics. Keep the failed partition ordered while
# allowing that dependency to converge, then use the existing DLQ recovery path instead of
# restarting this entire service indefinitely behind a permanently unresolved reference.
TRANSACTION_DEPENDENCY_RETRY_MAX_ELAPSED_SECONDS = 30

ConsumerFactory = Callable[..., BaseConsumer]
ExecutionProfileLoader = Callable[[str], KafkaConsumerExecutionProfile]


def build_transaction_processing_consumers(
    *,
    process_transaction: ProcessTransactionUseCase | None = None,
    route_corporate_action_child: RouteCorporateActionChildArrivalUseCase | None = None,
    replay_booked_transaction: ReplayBookedTransactionUseCase | None = None,
    handle_fixed_income_book_cost_authority: (
        HandleFixedIncomeBookCostAuthorityEventUseCase | None
    ) = None,
    handle_corporate_action_manifest: HandleCorporateActionManifestEventUseCase | None = None,
    transaction_consumer_factory: ConsumerFactory = TransactionProcessingConsumer,
    replay_request_consumer_factory: ConsumerFactory = BookedTransactionReplayRequestConsumer,
    fixed_income_authority_consumer_factory: ConsumerFactory = (
        FixedIncomeBookCostAuthorityConsumer
    ),
    fixed_income_correction_replay_consumer_factory: ConsumerFactory = (
        FixedIncomeBookCostCorrectionReplayConsumer
    ),
    corporate_action_manifest_consumer_factory: ConsumerFactory = CorporateActionManifestConsumer,
    execution_profile_loader: ExecutionProfileLoader = load_kafka_consumer_execution_profile,
    tenant_authority: TransactionTenantAuthorityPort | None = None,
) -> tuple[BaseConsumer, BaseConsumer, BaseConsumer, BaseConsumer, BaseConsumer]:
    """Compose transaction, replay, source-authority, and manifest consumers."""
    process_use_case = (
        process_transaction
        if process_transaction is not None
        else build_process_transaction_use_case()
    )
    replay_use_case = (
        replay_booked_transaction
        if replay_booked_transaction is not None
        else build_replay_booked_transaction_use_case()
    )
    authority_use_case = (
        handle_fixed_income_book_cost_authority
        if handle_fixed_income_book_cost_authority is not None
        else build_fixed_income_book_cost_authority_use_case(correction_replay_enabled=True)
    )
    corporate_action_arrival = (
        route_corporate_action_child
        if route_corporate_action_child is not None
        else build_corporate_action_child_arrival_use_case()
    )
    manifest_use_case = (
        handle_corporate_action_manifest
        if handle_corporate_action_manifest is not None
        else build_corporate_action_manifest_use_case()
    )
    live_execution_profile = execution_profile_loader(TRANSACTION_PROCESSING_CONSUMER_GROUP)
    replay_execution_profile = execution_profile_loader(TRANSACTION_REPLAY_REQUEST_CONSUMER_GROUP)
    authority_execution_profile = execution_profile_loader(
        FIXED_INCOME_BOOK_COST_AUTHORITY_CONSUMER_GROUP
    )
    correction_replay_execution_profile = execution_profile_loader(
        FIXED_INCOME_BOOK_COST_CORRECTION_REPLAY_CONSUMER_GROUP
    )
    manifest_execution_profile = execution_profile_loader(CORPORATE_ACTION_MANIFEST_CONSUMER_GROUP)
    live_consumer = transaction_consumer_factory(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        dlq_topic=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
        topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
        group_id=TRANSACTION_PROCESSING_CONSUMER_GROUP,
        service_prefix="TXNPROC",
        use_case=process_use_case,
        route_corporate_action_child=corporate_action_arrival,
        tenant_authority=(
            tenant_authority
            if tenant_authority is not None
            else SqlAlchemyTransactionTenantAuthority(get_async_session_factory())
        ),
        execution_profile=live_execution_profile,
        retryable_failure_max_elapsed_seconds=(TRANSACTION_DEPENDENCY_RETRY_MAX_ELAPSED_SECONDS),
    )
    replay_consumer = replay_request_consumer_factory(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        dlq_topic=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
        topic=KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
        group_id=TRANSACTION_REPLAY_REQUEST_CONSUMER_GROUP,
        service_prefix="TXNREPLAY",
        use_case=replay_use_case,
        execution_profile=replay_execution_profile,
        retryable_failure_max_elapsed_seconds=(TRANSACTION_DEPENDENCY_RETRY_MAX_ELAPSED_SECONDS),
    )
    authority_consumer = fixed_income_authority_consumer_factory(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        dlq_topic=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
        topic=KAFKA_FIXED_INCOME_BOOK_COST_AUTHORITY_RECEIVED_TOPIC,
        group_id=FIXED_INCOME_BOOK_COST_AUTHORITY_CONSUMER_GROUP,
        service_prefix="BOOKCOST",
        use_case=authority_use_case,
        execution_profile=authority_execution_profile,
        retryable_failure_max_elapsed_seconds=(TRANSACTION_DEPENDENCY_RETRY_MAX_ELAPSED_SECONDS),
    )
    correction_replay_consumer = fixed_income_correction_replay_consumer_factory(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        dlq_topic=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
        topic=KAFKA_FIXED_INCOME_BOOK_COST_DISPOSAL_REPLAY_REQUESTED_TOPIC,
        group_id=FIXED_INCOME_BOOK_COST_CORRECTION_REPLAY_CONSUMER_GROUP,
        service_prefix="BOOKCOSTREPLAY",
        use_case=replay_use_case,
        execution_profile=correction_replay_execution_profile,
        retryable_failure_max_elapsed_seconds=(TRANSACTION_DEPENDENCY_RETRY_MAX_ELAPSED_SECONDS),
    )
    manifest_consumer = corporate_action_manifest_consumer_factory(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        dlq_topic=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
        topic=KAFKA_CORPORATE_ACTION_MANIFEST_RECEIVED_TOPIC,
        group_id=CORPORATE_ACTION_MANIFEST_CONSUMER_GROUP,
        service_prefix="CAMANIFEST",
        use_case=manifest_use_case,
        execution_profile=manifest_execution_profile,
        retryable_failure_max_elapsed_seconds=(TRANSACTION_DEPENDENCY_RETRY_MAX_ELAPSED_SECONDS),
    )
    return (
        live_consumer,
        replay_consumer,
        authority_consumer,
        correction_replay_consumer,
        manifest_consumer,
    )
