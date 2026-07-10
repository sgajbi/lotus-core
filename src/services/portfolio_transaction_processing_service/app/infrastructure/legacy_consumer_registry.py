from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
    KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
    KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
    KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
)

from src.services.calculators.cashflow_calculator_service.app.consumers import (
    transaction_consumer as cashflow_consumer,
)
from src.services.calculators.cost_calculator_service.app.consumer import CostCalculatorConsumer
from src.services.calculators.cost_calculator_service.app.consumers import (
    reprocessing_consumer,
)
from src.services.calculators.position_calculator.app.consumers import (
    transaction_event_consumer,
)


@dataclass(frozen=True, slots=True)
class LegacyTransactionConsumerFactories:
    cost: Callable[..., Any] = CostCalculatorConsumer
    cost_reprocessing: Callable[..., Any] = reprocessing_consumer.ReprocessingConsumer
    cashflow: Callable[..., Any] = cashflow_consumer.CashflowCalculatorConsumer
    position: Callable[..., Any] = transaction_event_consumer.TransactionEventConsumer


def build_legacy_transaction_consumers(
    *,
    factories: LegacyTransactionConsumerFactories = LegacyTransactionConsumerFactories(),
) -> tuple[Any, ...]:
    """Build compatibility consumers with their existing topics and group identities."""
    shared = {
        "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
        "dlq_topic": KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    }
    return (
        factories.cost(
            **shared,
            topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
            group_id="cost_calculator_group",
            service_prefix="COST",
        ),
        factories.cost_reprocessing(
            **shared,
            topic=KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
            group_id="cost_reprocessing_group",
            service_prefix="COST_REPRO",
        ),
        factories.cashflow(
            **shared,
            topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
            group_id="cashflow_calculator_group",
            service_prefix="CFLOW",
        ),
        factories.cashflow(
            **shared,
            topic=KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
            group_id="cashflow_calculator_group_replay",
            service_prefix="CFLOW",
        ),
        factories.position(
            **shared,
            topic=KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
            group_id="position_calculator_group_gated",
            service_prefix="POS",
        ),
        factories.position(
            **shared,
            topic=KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
            group_id="position_calculator_group_replay",
            service_prefix="POS",
        ),
    )
