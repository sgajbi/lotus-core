"""Tests for final transaction consumer runtime composition."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile

from src.services.portfolio_transaction_processing_service.app.runtime import (
    consumer_composition,
)


class _RecordedConsumer(MagicMock):
    def __init__(
        self,
        *,
        family: str,
        calls: list[tuple[str, dict[str, Any]]],
        **kwargs: Any,
    ) -> None:
        super().__init__(spec=BaseConsumer)
        self.family = family
        self.topic = kwargs["topic"]
        calls.append((family, kwargs))


def _recording_factory(
    family: str,
    calls: list[tuple[str, dict[str, Any]]],
):
    def build(**kwargs: Any) -> BaseConsumer:
        return _RecordedConsumer(family=family, calls=calls, **kwargs)

    return build


def test_composition_builds_exactly_one_live_and_one_replay_request_consumer() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    process_use_case = MagicMock()
    replay_use_case = MagicMock()

    consumers = consumer_composition.build_transaction_processing_consumers(
        process_transaction=process_use_case,
        replay_booked_transaction=replay_use_case,
        transaction_consumer_factory=_recording_factory("live", calls),
        replay_request_consumer_factory=_recording_factory("replay_request", calls),
    )

    assert len(consumers) == 2
    assert [family for family, _ in calls] == ["live", "replay_request"]
    live = calls[0][1]
    assert live["topic"] == "transactions.persisted"
    assert live["group_id"] == "portfolio_transaction_processing_group"
    assert live["service_prefix"] == "TXNPROC"
    assert live["use_case"] is process_use_case
    assert live["retryable_failure_max_elapsed_seconds"] == 30
    replay = calls[1][1]
    assert replay["topic"] == "transactions.reprocessing.requested"
    assert replay["group_id"] == "portfolio_transaction_replay_request_group"
    assert replay["service_prefix"] == "TXNREPLAY"
    assert replay["use_case"] is replay_use_case
    assert replay["retryable_failure_max_elapsed_seconds"] == 30
    assert all(values["dlq_topic"] == "dlq.persistence_service" for _, values in calls)


def test_composition_builds_each_application_use_case_once(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    process_use_case = MagicMock()
    replay_use_case = MagicMock()
    process_builder = MagicMock(return_value=process_use_case)
    replay_builder = MagicMock(return_value=replay_use_case)
    monkeypatch.setattr(
        consumer_composition,
        "build_process_transaction_use_case",
        process_builder,
    )
    monkeypatch.setattr(
        consumer_composition,
        "build_replay_booked_transaction_use_case",
        replay_builder,
    )

    consumer_composition.build_transaction_processing_consumers(
        transaction_consumer_factory=_recording_factory("live", calls),
        replay_request_consumer_factory=_recording_factory("replay_request", calls),
    )

    process_builder.assert_called_once_with()
    replay_builder.assert_called_once_with()
    assert calls[0][1]["use_case"] is process_use_case
    assert calls[1][1]["use_case"] is replay_use_case


def test_composition_loads_independent_live_and_replay_execution_profiles() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    live_profile = MagicMock(spec=KafkaConsumerExecutionProfile)
    replay_profile = MagicMock(spec=KafkaConsumerExecutionProfile)
    profile_loader = MagicMock(side_effect=[live_profile, replay_profile])

    consumer_composition.build_transaction_processing_consumers(
        process_transaction=MagicMock(),
        replay_booked_transaction=MagicMock(),
        transaction_consumer_factory=_recording_factory("live", calls),
        replay_request_consumer_factory=_recording_factory("replay_request", calls),
        execution_profile_loader=profile_loader,
    )

    assert [item.args[0] for item in profile_loader.call_args_list] == [
        "portfolio_transaction_processing_group",
        "portfolio_transaction_replay_request_group",
    ]
    assert calls[0][1]["execution_profile"] is live_profile
    assert calls[1][1]["execution_profile"] is replay_profile
