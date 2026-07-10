from __future__ import annotations

from pathlib import Path
from typing import Any

from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    legacy_consumer_registry as registry,
)


class _RecordedConsumer:
    def __init__(self, *, family: str, calls: list[tuple[str, dict[str, Any]]], **kwargs: Any):
        self.family = family
        self.topic = kwargs["topic"]
        calls.append((family, kwargs))


def test_registry_preserves_current_consumer_topics_groups_and_prefixes() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def factory(family: str):
        return lambda **kwargs: _RecordedConsumer(family=family, calls=calls, **kwargs)

    consumers = registry.build_legacy_transaction_consumers(
        factories=registry.LegacyTransactionConsumerFactories(
            cost=factory("cost"),
            cost_reprocessing=factory("cost_reprocessing"),
            cashflow=factory("cashflow"),
            position=factory("position"),
        )
    )

    assert len(consumers) == 6
    assert [
        (family, values["topic"], values["group_id"], values["service_prefix"])
        for family, values in calls
    ] == [
        ("cost", "transactions.persisted", "cost_calculator_group", "COST"),
        (
            "cost_reprocessing",
            "transactions.reprocessing.requested",
            "cost_reprocessing_group",
            "COST_REPRO",
        ),
        ("cashflow", "transactions.persisted", "cashflow_calculator_group", "CFLOW"),
        (
            "cashflow",
            "transactions.cost.processed",
            "cashflow_calculator_group_replay",
            "CFLOW",
        ),
        (
            "position",
            "transaction_processing.ready",
            "position_calculator_group_gated",
            "POS",
        ),
        (
            "position",
            "transactions.cost.processed",
            "position_calculator_group_replay",
            "POS",
        ),
    ]
    assert all(values["dlq_topic"] == "dlq.persistence_service" for _, values in calls)


def test_legacy_calculator_imports_are_confined_to_infrastructure_adapters() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    service_root = repo_root / "src/services/portfolio_transaction_processing_service"
    legacy_import_files = [
        source.relative_to(service_root).as_posix()
        for source in service_root.rglob("*.py")
        if "src.services.calculators" in source.read_text(encoding="utf-8")
    ]

    assert legacy_import_files == [
        "app/infrastructure/cost_processing_adapter.py",
        "app/infrastructure/legacy_consumer_registry.py",
    ]
