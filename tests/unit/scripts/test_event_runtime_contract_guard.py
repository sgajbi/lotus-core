from pathlib import Path

from portfolio_common.event_supportability import DirectKafkaTopicDefinition, EventFamilyDefinition

from scripts import event_runtime_contract_guard as guard


def test_discover_outbox_event_emissions_finds_current_runtime_outbox_contracts() -> None:
    emissions = guard.discover_outbox_event_emissions()
    emitted_contracts = {(emission.event_type, emission.topic) for emission in emissions}

    assert ("RawTransactionPersisted", "transactions.persisted") in emitted_contracts
    assert ("ProcessedTransactionPersisted", "transactions.cost.processed") in emitted_contracts
    assert ("CashflowCalculated", "cashflows.calculated") in emitted_contracts
    assert (
        "PortfolioAggregationDayCompleted",
        "portfolio_day.aggregation.completed",
    ) in emitted_contracts


def test_current_runtime_uses_event_publisher_ports_instead_of_direct_kafka_publishes() -> None:
    publishes = guard.discover_direct_kafka_publishes()

    assert publishes == ()


def test_discover_consumer_dlq_wirings_finds_current_base_consumer_topics() -> None:
    wirings = guard.discover_consumer_dlq_topic_wirings()
    topics = {wiring.topic for wiring in wirings}
    consumer_names = {wiring.consumer_name for wiring in wirings}

    assert "dlq.persistence_service" in topics
    assert "PortfolioConsumer" in consumer_names
    assert "CostCalculatorConsumer" in consumer_names


def test_evaluate_outbox_event_contracts_accepts_current_runtime_emissions() -> None:
    assert guard.evaluate_outbox_event_contracts() == []


def test_evaluate_outbox_event_contracts_rejects_missing_catalog_event() -> None:
    errors = guard.evaluate_outbox_event_contracts(
        (
            guard.OutboxEventEmission(
                source="src/example.py",
                function_name="publish",
                event_type="UnknownEvent",
                topic="unknown.topic",
            ),
        ),
        direct_publishes=(),
    )

    assert errors == [
        "src/example.py:publish: UnknownEvent emits an outbox event missing from the "
        "RFC-0083 event supportability catalog"
    ]


def test_evaluate_outbox_event_contracts_rejects_invalid_event_catalog() -> None:
    invalid_definitions = (
        EventFamilyDefinition(
            event_type="CashflowCalculated",
            schema_model="MissingCashflowEvent",
            family="domain_state_event",
            direction="outbound",
            aggregate_type="cashflow",
            topic="cashflows.calculated",
            producer_service="cashflow_calculator_service",
            consumer_services=("pipeline_orchestrator_service",),
            idempotency_required=True,
            correlation_required=True,
            schema_version_required=True,
            source_data_products=("TransactionLedgerWindow",),
        ),
    )

    errors = guard.evaluate_outbox_event_contracts(
        (
            guard.OutboxEventEmission(
                source="src/example.py",
                function_name="publish",
                event_type="CashflowCalculated",
                topic="cashflows.calculated",
            ),
        ),
        event_definitions=invalid_definitions,
        direct_publishes=(),
    )

    assert errors == [
        "event supportability catalog is invalid: CashflowCalculated references missing "
        "schema model: MissingCashflowEvent"
    ]


def test_evaluate_outbox_event_contracts_rejects_topic_drift() -> None:
    errors = guard.evaluate_outbox_event_contracts(
        (
            guard.OutboxEventEmission(
                source="src/example.py",
                function_name="publish",
                event_type="CashflowCalculated",
                topic="cashflow.calculated",
            ),
        ),
        direct_publishes=(),
    )

    assert errors == [
        "src/example.py:publish: CashflowCalculated emits topic 'cashflow.calculated', "
        "expected 'cashflows.calculated'"
    ]


def test_evaluate_outbox_event_contracts_rejects_uncataloged_direct_kafka_publish() -> None:
    errors = guard.evaluate_outbox_event_contracts(
        emissions=(),
        direct_publishes=(
            guard.DirectKafkaPublish(
                source="src/example.py",
                function_name="publish",
                topic="uncataloged.topic",
            ),
        ),
    )

    assert errors == [
        "src/example.py:publish: uncataloged.topic publishes a direct Kafka topic missing "
        "from the RFC-0083 direct Kafka topic catalog"
    ]


def test_evaluate_outbox_event_contracts_rejects_uncataloged_dlq_topic() -> None:
    errors = guard.evaluate_outbox_event_contracts(
        emissions=(),
        direct_publishes=(),
        consumer_dlq_wirings=(
            guard.ConsumerDlqTopicWiring(
                source="src/example.py",
                function_name="build",
                consumer_name="ExampleConsumer",
                topic="uncataloged.dlq",
                expression='"uncataloged.dlq"',
            ),
        ),
    )

    assert errors == [
        "src/example.py:build: ExampleConsumer wires DLQ topic 'uncataloged.dlq' missing from "
        "the RFC-0083 direct Kafka topic catalog"
    ]


def test_evaluate_outbox_event_contracts_rejects_unresolved_dlq_topic() -> None:
    errors = guard.evaluate_outbox_event_contracts(
        emissions=(),
        direct_publishes=(),
        consumer_dlq_wirings=(
            guard.ConsumerDlqTopicWiring(
                source="src/example.py",
                function_name="build",
                consumer_name="ExampleConsumer",
                topic=None,
                expression="settings.dlq_topic",
            ),
        ),
    )

    assert errors == [
        "src/example.py:build: ExampleConsumer wires an unresolved BaseConsumer DLQ topic "
        "expression 'settings.dlq_topic'"
    ]


def test_discover_outbox_event_emissions_resolves_literal_and_config_topics(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "producer.py"
    source_file.write_text(
        """
from portfolio_common.config import KAFKA_CASHFLOWS_CALCULATED_TOPIC

def publish_direct(repo):
    repo.create_outbox_event(
        aggregate_id="p1",
        event_type="CashflowCalculated",
        topic=KAFKA_CASHFLOWS_CALCULATED_TOPIC,
        payload={},
    )

def publish_dict():
    return {
        "event_type": "FinancialReconciliationRequested",
        "topic": "portfolio_day.reconciliation.requested",
    }
""",
        encoding="utf-8",
    )

    emissions = guard.discover_outbox_event_emissions(source_root=tmp_path)

    assert emissions == (
        guard.OutboxEventEmission(
            source="producer.py",
            function_name="publish_direct",
            event_type="CashflowCalculated",
            topic="cashflows.calculated",
        ),
        guard.OutboxEventEmission(
            source="producer.py",
            function_name="publish_dict",
            event_type="FinancialReconciliationRequested",
            topic="portfolio_day.reconciliation.requested",
        ),
    )


def test_discover_direct_kafka_publishes_resolves_literal_and_config_topics(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "producer.py"
    source_file.write_text(
        """
from portfolio_common.config import KAFKA_TRANSACTIONS_RAW_RECEIVED_TOPIC

def publish_direct(producer):
    producer.publish_message(
        topic=KAFKA_TRANSACTIONS_RAW_RECEIVED_TOPIC,
        key="P1",
        value={},
    )

def publish_literal(producer):
    producer.publish_message(
        topic="portfolios.raw.received",
        key="P1",
        value={},
    )
""",
        encoding="utf-8",
    )

    publishes = guard.discover_direct_kafka_publishes(source_root=tmp_path)

    assert publishes == (
        guard.DirectKafkaPublish(
            source="producer.py",
            function_name="publish_literal",
            topic="portfolios.raw.received",
        ),
        guard.DirectKafkaPublish(
            source="producer.py",
            function_name="publish_direct",
            topic="transactions.raw.received",
        ),
    )


def test_discover_consumer_dlq_wirings_resolves_literal_config_alias_and_dynamic(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "consumer_manager.py"
    source_file.write_text(
        """
from portfolio_common.config import KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC
from portfolio_common.kafka_consumer import BaseConsumer

class ExampleConsumer(BaseConsumer):
    pass

class ChildConsumer(ExampleConsumer):
    pass

def build_config():
    dlq_topic = KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC
    return ExampleConsumer(
        bootstrap_servers="kafka:9092",
        topic="transactions.raw.received",
        group_id="example",
        dlq_topic=dlq_topic,
    )

def build_literal():
    return ChildConsumer(
        bootstrap_servers="kafka:9092",
        topic="transactions.raw.received",
        group_id="example",
        dlq_topic="literal.dlq",
    )

def build_dynamic(settings):
    return ExampleConsumer(
        bootstrap_servers="kafka:9092",
        topic="transactions.raw.received",
        group_id="example",
        dlq_topic=settings.dlq_topic,
    )
""",
        encoding="utf-8",
    )

    wirings = guard.discover_consumer_dlq_topic_wirings(source_root=tmp_path)
    by_function = {wiring.function_name: wiring for wiring in wirings}

    assert by_function["build_config"] == guard.ConsumerDlqTopicWiring(
        source="consumer_manager.py",
        function_name="build_config",
        consumer_name="ExampleConsumer",
        topic="dlq.persistence_service",
        expression="dlq_topic",
    )
    assert by_function["build_literal"] == guard.ConsumerDlqTopicWiring(
        source="consumer_manager.py",
        function_name="build_literal",
        consumer_name="ChildConsumer",
        topic="literal.dlq",
        expression="'literal.dlq'",
    )
    assert by_function["build_dynamic"] == guard.ConsumerDlqTopicWiring(
        source="consumer_manager.py",
        function_name="build_dynamic",
        consumer_name="ExampleConsumer",
        topic=None,
        expression="settings.dlq_topic",
    )


def test_evaluate_outbox_event_contracts_accepts_cataloged_literal_and_config_dlq_topics(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "consumer_manager.py"
    source_file.write_text(
        """
from portfolio_common.config import KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC
from portfolio_common.kafka_consumer import BaseConsumer

class ExampleConsumer(BaseConsumer):
    pass

def build_config():
    return ExampleConsumer(
        bootstrap_servers="kafka:9092",
        topic="transactions.raw.received",
        group_id="example",
        dlq_topic=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    )

def build_literal():
    return ExampleConsumer(
        bootstrap_servers="kafka:9092",
        topic="transactions.raw.received",
        group_id="example",
        dlq_topic="literal.dlq",
    )
""",
        encoding="utf-8",
    )
    literal_dlq_definition = DirectKafkaTopicDefinition(
        name="LiteralDlq",
        topic="literal.dlq",
        semantic_type="consumer_dlq",
        producer_service="BaseConsumer",
        consumer_services=("event_replay_service",),
        payload_contract="base_consumer_dlq_payload",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=("IngestionEvidenceBundle",),
    )

    errors = guard.evaluate_outbox_event_contracts(
        emissions=(),
        direct_publishes=(),
        direct_topic_definitions=(
            *guard.DIRECT_KAFKA_TOPIC_DEFINITIONS,
            literal_dlq_definition,
        ),
        consumer_dlq_wirings=guard.discover_consumer_dlq_topic_wirings(source_root=tmp_path),
    )

    assert errors == []
