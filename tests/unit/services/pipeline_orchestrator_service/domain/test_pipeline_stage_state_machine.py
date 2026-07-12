from dataclasses import dataclass

from src.services.pipeline_orchestrator_service.app.domain.pipeline_stage_state_machine import (
    decide_transaction_stage_readiness,
    is_control_stage_blocking,
    should_emit_control_stage_for_epoch,
    should_register_transaction_stage_for_epoch,
)


@dataclass
class _Stage:
    status: str
    cost_event_seen: bool
    cashflow_event_seen: bool


def test_transaction_stage_waits_for_missing_cost_signal_without_outbox_dependency() -> None:
    decision = decide_transaction_stage_readiness(
        _Stage(status="PENDING", cost_event_seen=False, cashflow_event_seen=True)
    )

    assert decision.should_complete is False
    assert decision.reason_code == "missing_transaction_processing_event"


def test_transaction_stage_uses_authoritative_processing_signal_without_cashflow_fan_in() -> None:
    decision = decide_transaction_stage_readiness(
        _Stage(status="PENDING", cost_event_seen=True, cashflow_event_seen=False)
    )

    assert decision.should_complete is True
    assert decision.reason_code == "ready"


def test_transaction_stage_is_ready_when_compatibility_flags_are_seen() -> None:
    decision = decide_transaction_stage_readiness(
        _Stage(status="PENDING", cost_event_seen=True, cashflow_event_seen=True)
    )

    assert decision.should_complete is True
    assert decision.reason_code == "ready"


def test_completed_transaction_stage_does_not_reemit() -> None:
    decision = decide_transaction_stage_readiness(
        _Stage(status="COMPLETED", cost_event_seen=True, cashflow_event_seen=True)
    )

    assert decision.should_complete is False
    assert decision.reason_code == "already_completed"


def test_control_stage_blocking_statuses_are_explicit() -> None:
    assert is_control_stage_blocking("FAILED") is True
    assert is_control_stage_blocking("REQUIRES_REPLAY") is True
    assert is_control_stage_blocking("COMPLETED") is False


def test_control_stage_latest_epoch_blocks_stale_emission() -> None:
    assert should_emit_control_stage_for_epoch(latest_epoch=None, event_epoch=2) is True
    assert should_emit_control_stage_for_epoch(latest_epoch=2, event_epoch=2) is True
    assert should_emit_control_stage_for_epoch(latest_epoch=3, event_epoch=2) is False


def test_transaction_stage_epoch_fence_accepts_current_or_newer_events_only() -> None:
    assert should_register_transaction_stage_for_epoch(latest_epoch=None, event_epoch=0) is True
    assert should_register_transaction_stage_for_epoch(latest_epoch=1, event_epoch=1) is True
    assert should_register_transaction_stage_for_epoch(latest_epoch=1, event_epoch=2) is True
    assert should_register_transaction_stage_for_epoch(latest_epoch=1, event_epoch=0) is False
