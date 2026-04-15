from pathlib import Path

from portfolio_common.event_supportability import EventFamilyDefinition
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
        )
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
        )
    )

    assert errors == [
        "src/example.py:publish: CashflowCalculated emits topic 'cashflow.calculated', "
        "expected 'cashflows.calculated'"
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
