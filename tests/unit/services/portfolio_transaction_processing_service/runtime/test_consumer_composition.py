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


def test_composition_builds_transaction_replay_authority_and_correction_consumers() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    process_use_case = MagicMock()
    replay_use_case = MagicMock()
    authority_use_case = MagicMock()
    manifest_use_case = MagicMock()

    consumers = consumer_composition.build_transaction_processing_consumers(
        process_transaction=process_use_case,
        replay_booked_transaction=replay_use_case,
        handle_fixed_income_book_cost_authority=authority_use_case,
        handle_corporate_action_manifest=manifest_use_case,
        transaction_consumer_factory=_recording_factory("live", calls),
        replay_request_consumer_factory=_recording_factory("replay_request", calls),
        fixed_income_authority_consumer_factory=_recording_factory("authority", calls),
        fixed_income_correction_replay_consumer_factory=_recording_factory(
            "correction_replay", calls
        ),
        corporate_action_manifest_consumer_factory=_recording_factory("manifest", calls),
    )

    assert len(consumers) == 5
    assert [family for family, _ in calls] == [
        "live",
        "replay_request",
        "authority",
        "correction_replay",
        "manifest",
    ]
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
    authority = calls[2][1]
    assert authority["topic"] == "fixed_income.book_cost.authority.received"
    assert authority["group_id"] == "fixed_income_book_cost_authority_group"
    assert authority["service_prefix"] == "BOOKCOST"
    assert authority["use_case"] is authority_use_case
    assert authority["retryable_failure_max_elapsed_seconds"] == 30
    correction_replay = calls[3][1]
    assert correction_replay["topic"] == "fixed_income.book_cost.disposal_replay.requested"
    assert correction_replay["group_id"] == "fixed_income_book_cost_correction_replay_group"
    assert correction_replay["service_prefix"] == "BOOKCOSTREPLAY"
    assert correction_replay["use_case"] is replay_use_case
    assert correction_replay["retryable_failure_max_elapsed_seconds"] == 30
    manifest = calls[4][1]
    assert manifest["topic"] == "corporate_action.manifest.received"
    assert manifest["group_id"] == "corporate_action_manifest_group"
    assert manifest["service_prefix"] == "CAMANIFEST"
    assert manifest["use_case"] is manifest_use_case
    assert manifest["retryable_failure_max_elapsed_seconds"] == 30
    assert all(values["dlq_topic"] == "dlq.persistence_service" for _, values in calls)


def test_composition_builds_each_application_use_case_once(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    process_use_case = MagicMock()
    replay_use_case = MagicMock()
    process_builder = MagicMock(return_value=process_use_case)
    replay_builder = MagicMock(return_value=replay_use_case)
    authority_use_case = MagicMock()
    authority_builder = MagicMock(return_value=authority_use_case)
    manifest_use_case = MagicMock()
    manifest_builder = MagicMock(return_value=manifest_use_case)
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
    monkeypatch.setattr(
        consumer_composition,
        "build_fixed_income_book_cost_authority_use_case",
        authority_builder,
    )
    monkeypatch.setattr(
        consumer_composition,
        "build_corporate_action_manifest_use_case",
        manifest_builder,
    )

    consumer_composition.build_transaction_processing_consumers(
        transaction_consumer_factory=_recording_factory("live", calls),
        replay_request_consumer_factory=_recording_factory("replay_request", calls),
        fixed_income_authority_consumer_factory=_recording_factory("authority", calls),
        fixed_income_correction_replay_consumer_factory=_recording_factory(
            "correction_replay", calls
        ),
        corporate_action_manifest_consumer_factory=_recording_factory("manifest", calls),
    )

    process_builder.assert_called_once_with()
    replay_builder.assert_called_once_with()
    authority_builder.assert_called_once_with(correction_replay_enabled=True)
    manifest_builder.assert_called_once_with()
    assert calls[0][1]["use_case"] is process_use_case
    assert calls[1][1]["use_case"] is replay_use_case
    assert calls[2][1]["use_case"] is authority_use_case
    assert calls[3][1]["use_case"] is replay_use_case
    assert calls[4][1]["use_case"] is manifest_use_case


def test_composition_loads_independent_live_and_replay_execution_profiles() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    live_profile = MagicMock(spec=KafkaConsumerExecutionProfile)
    replay_profile = MagicMock(spec=KafkaConsumerExecutionProfile)
    authority_profile = MagicMock(spec=KafkaConsumerExecutionProfile)
    correction_replay_profile = MagicMock(spec=KafkaConsumerExecutionProfile)
    manifest_profile = MagicMock(spec=KafkaConsumerExecutionProfile)
    profile_loader = MagicMock(
        side_effect=[
            live_profile,
            replay_profile,
            authority_profile,
            correction_replay_profile,
            manifest_profile,
        ]
    )

    consumer_composition.build_transaction_processing_consumers(
        process_transaction=MagicMock(),
        replay_booked_transaction=MagicMock(),
        handle_fixed_income_book_cost_authority=MagicMock(),
        handle_corporate_action_manifest=MagicMock(),
        transaction_consumer_factory=_recording_factory("live", calls),
        replay_request_consumer_factory=_recording_factory("replay_request", calls),
        fixed_income_authority_consumer_factory=_recording_factory("authority", calls),
        fixed_income_correction_replay_consumer_factory=_recording_factory(
            "correction_replay", calls
        ),
        corporate_action_manifest_consumer_factory=_recording_factory("manifest", calls),
        execution_profile_loader=profile_loader,
    )

    assert [item.args[0] for item in profile_loader.call_args_list] == [
        "portfolio_transaction_processing_group",
        "portfolio_transaction_replay_request_group",
        "fixed_income_book_cost_authority_group",
        "fixed_income_book_cost_correction_replay_group",
        "corporate_action_manifest_group",
    ]
    assert calls[0][1]["execution_profile"] is live_profile
    assert calls[1][1]["execution_profile"] is replay_profile
    assert calls[2][1]["execution_profile"] is authority_profile
    assert calls[3][1]["execution_profile"] is correction_replay_profile
    assert calls[4][1]["execution_profile"] is manifest_profile
