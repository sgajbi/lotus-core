"""Tests for financial reconciliation control-stage domain policy."""

from src.services.financial_reconciliation_service.app.domain.reconciliation_control import (
    is_control_blocking,
    merge_control_status,
    should_emit_controls_for_epoch,
)


def test_control_status_merge_preserves_highest_severity() -> None:
    assert merge_control_status("REQUIRES_REPLAY", "COMPLETED") == "REQUIRES_REPLAY"
    assert merge_control_status("COMPLETED", "FAILED") == "FAILED"


def test_control_blocking_statuses_match_reconciliation_replay_policy() -> None:
    assert is_control_blocking("REQUIRES_REPLAY") is True
    assert is_control_blocking("FAILED") is True
    assert is_control_blocking("COMPLETED") is False


def test_controls_emit_only_for_latest_epoch() -> None:
    assert should_emit_controls_for_epoch(latest_epoch=4, completed_epoch=4) is True
    assert should_emit_controls_for_epoch(latest_epoch=4, completed_epoch=3) is False
    assert should_emit_controls_for_epoch(latest_epoch=None, completed_epoch=1) is True
