"""Test position-history Prometheus and structured-log observations."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from src.services.portfolio_transaction_processing_service.app.domain import (
    BookedTransaction,
    PositionRecalculationState,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.prometheus_position_history_observer import (  # noqa: E501
    PrometheusPositionHistoryObserver,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    PositionRecalculationReason,
    PositionReplayMode,
)


def _transaction() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="SGD",
        currency="SGD",
    )


def _state() -> PositionRecalculationState:
    return PositionRecalculationState(
        portfolio_id="PB-001",
        security_id="SEC-001",
        epoch=4,
        watermark_date=date(2026, 4, 9),
        status="REPROCESSING",
    )


@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure."
    "prometheus_position_history_observer.POSITION_RECALCULATION_WORK_ITEMS"
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure."
    "prometheus_position_history_observer.POSITION_RECALCULATION_COORDINATION_TOTAL"
)
def test_observer_preserves_coordination_and_work_metric_labels(
    coordination_metric,
    work_metric,
) -> None:
    observer = PrometheusPositionHistoryObserver()

    observer.recalculation_coalesced(
        transaction=_transaction(),
        epoch=4,
        reason=PositionRecalculationReason.ALREADY_MATERIALIZED,
    )
    observer.replay_work_items(mode=PositionReplayMode.COALESCED, count=0)

    coordination_metric.labels.assert_called_once_with(
        outcome="coalesced",
        reason="already_materialized",
    )
    coordination_metric.labels.return_value.inc.assert_called_once_with()
    work_metric.labels.assert_called_once_with(mode="coalesced")
    work_metric.labels.return_value.observe.assert_called_once_with(0)


@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure."
    "prometheus_position_history_observer.logger"
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure."
    "prometheus_position_history_observer.EPOCH_MISMATCH_DROPPED_TOTAL"
)
def test_observer_preserves_stale_epoch_metric_and_structured_taxonomy(
    epoch_metric,
    logger,
) -> None:
    observer = PrometheusPositionHistoryObserver()
    transaction = _transaction()

    observer.stale_epoch_discarded(transaction=transaction, current_epoch=4)

    epoch_metric.labels.assert_called_once_with(
        service_name="position-calculator",
        topic="<unknown>",
    )
    epoch_metric.labels.return_value.inc.assert_called_once_with()
    extra = logger.warning.call_args.kwargs["extra"]
    assert extra["reason_code"] == "stale_epoch"
    assert extra["event_name"] == "position_command_discarded"
    assert extra["operation"] == "materialize_position_history"
    assert extra["status"] == "skipped"


@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure."
    "prometheus_position_history_observer.REPROCESSING_EPOCH_BUMPED_TOTAL"
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure."
    "prometheus_position_history_observer.POSITION_RECALCULATION_COORDINATION_TOTAL"
)
def test_observer_preserves_backdated_epoch_metrics(coordination_metric, epoch_metric) -> None:
    observer = PrometheusPositionHistoryObserver()

    observer.epoch_advanced(transaction=_transaction(), state=_state())

    epoch_metric.labels.assert_called_once_with(trigger="backdated_transaction")
    epoch_metric.labels.return_value.inc.assert_called_once_with()
    coordination_metric.labels.assert_called_once_with(
        outcome="epoch_advanced",
        reason="backdated_transaction",
    )


@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure."
    "prometheus_position_history_observer.logger"
)
def test_observer_emits_structured_rebuild_and_generation_logs(logger) -> None:
    observer = PrometheusPositionHistoryObserver()
    transaction = _transaction()

    observer.backdated_recalculation_detected(
        transaction=transaction,
        current_state=_state(),
        effective_completed_date=date(2026, 4, 20),
        latest_history_date=date(2026, 4, 19),
    )
    observer.history_rebuilt(
        transaction=transaction,
        epoch=4,
        record_count=3,
        earliest_transaction_date=date(2026, 4, 10),
    )
    observer.generation_rearmed(
        portfolio_id="PB-001",
        security_id="SEC-001",
        epoch=4,
        transaction_date=date(2026, 4, 10),
        watermark_date=date(2026, 4, 9),
    )

    logger.warning.assert_called_once()
    assert logger.info.call_count == 2
    assert logger.warning.call_args.kwargs["extra"]["backdated_handling"] == "inline_rebuild"
    assert logger.info.call_args_list[0].kwargs["extra"]["position_record_count"] == 3
    assert logger.info.call_args_list[1].kwargs["extra"]["new_watermark_date"] == "2026-04-09"


@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure."
    "prometheus_position_history_observer.logger"
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure."
    "prometheus_position_history_observer.POSITION_RECALCULATION_COORDINATION_TOTAL"
)
def test_observer_contains_telemetry_failure(metric, logger) -> None:
    metric.labels.side_effect = RuntimeError("metrics unavailable")
    observer = PrometheusPositionHistoryObserver()

    observer.recalculation_coalesced(
        transaction=_transaction(),
        epoch=4,
        reason=PositionRecalculationReason.STALE_EPOCH,
    )

    logger.exception.assert_called_once()
