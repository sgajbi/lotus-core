from src.services.pipeline_orchestrator_service.app.domain.pipeline_stage_state_machine import (
    is_control_stage_blocking,
    should_emit_control_stage_for_epoch,
)


def test_control_stage_blocking_statuses_are_explicit() -> None:
    assert is_control_stage_blocking("FAILED") is True
    assert is_control_stage_blocking("REQUIRES_REPLAY") is True
    assert is_control_stage_blocking("COMPLETED") is False


def test_control_stage_latest_epoch_blocks_stale_emission() -> None:
    assert should_emit_control_stage_for_epoch(latest_epoch=None, event_epoch=2) is True
    assert should_emit_control_stage_for_epoch(latest_epoch=2, event_epoch=2) is True
    assert should_emit_control_stage_for_epoch(latest_epoch=3, event_epoch=2) is False
