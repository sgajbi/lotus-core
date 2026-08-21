from __future__ import annotations

from collections.abc import Iterator

import pytest

from scripts.validation.kafka_restart_recovery import (
    BrokerState,
    KafkaRestartRecoveryError,
    dependency_gated_recovery_command,
    recovery_failure_diagnostic,
    wait_for_healthy_broker,
)


def _states(*states: BrokerState) -> Iterator[BrokerState]:
    yield from states


def test_wait_for_healthy_broker_accepts_bounded_restart_recovery() -> None:
    states = _states(
        BrokerState("new", "starting", 0),
        BrokerState("new", "starting", 1),
        BrokerState("new", "healthy", 2),
    )
    clock = iter((0.0, 1.0, 2.0, 3.0, 4.0))

    recovered = wait_for_healthy_broker(
        lambda: next(states),
        timeout_seconds=10,
        poll_interval_seconds=0,
        sleeper=lambda _: None,
        monotonic=lambda: next(clock),
    )

    assert recovered == BrokerState("new", "healthy", 2)


def test_wait_for_healthy_broker_fails_with_safe_operator_diagnostic() -> None:
    state = BrokerState("new", "exited", 5)
    clock = iter((0.0, 11.0))

    with pytest.raises(KafkaRestartRecoveryError) as exc_info:
        wait_for_healthy_broker(
            lambda: state,
            timeout_seconds=10,
            poll_interval_seconds=0,
            sleeper=lambda _: None,
            monotonic=lambda: next(clock),
        )

    message = str(exc_info.value)
    assert "restart_count=5" in message
    assert "live competing broker session" in message
    assert "do not delete ZooKeeper or application volumes" in message


def test_recovery_diagnostic_contains_no_destructive_instruction() -> None:
    message = recovery_failure_diagnostic(
        BrokerState("container-secret", "unhealthy", 5),
        timeout_seconds=90,
    )

    assert "container-secret" not in message
    assert "docker volume rm" not in message
    assert "down -v" not in message


def test_recovery_starts_through_topic_creator_dependency() -> None:
    command = dependency_gated_recovery_command(
        lambda *args: ["docker", "compose", "-p", "isolated", *args]
    )

    assert command == [
        "docker",
        "compose",
        "-p",
        "isolated",
        "up",
        "-d",
        "--force-recreate",
        "kafka-topic-creator",
    ]
    assert command[-1] != "kafka"
