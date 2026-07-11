"""Orchestrate deterministic cost-basis calculation over transaction timelines."""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

from portfolio_common.cost_basis import CostBasisMethod, normalize_cost_basis_method

from ..domain.cost_basis import (
    AverageCostBasisStrategy,
    CostBasisCalculator,
    CostBasisStrategy,
    CostBasisTransaction,
    CostCalculationError,
    CostCalculationErrorCollector,
    CostTransactionParser,
    CostTransactionSorter,
    FIFOBasisStrategy,
    LotDispositionEngine,
    OpenLotState,
)
from ..ports import CostBasisCalculationObservation, CostBasisCalculationObserver

logger = logging.getLogger(__name__)


def build_cost_basis_timeline_processor(
    cost_basis_method: str | CostBasisMethod = CostBasisMethod.FIFO,
    *,
    observer: CostBasisCalculationObserver | None = None,
) -> CostBasisTimelineProcessor:
    """Build a cost-basis timeline processor for the governed calculation method."""
    error_reporter = CostCalculationErrorCollector()
    resolved_method = normalize_cost_basis_method(cost_basis_method)
    strategy: CostBasisStrategy
    if resolved_method is CostBasisMethod.AVCO:
        strategy = AverageCostBasisStrategy()
        logger.debug("Using AVCO strategy for cost basis calculation.")
    else:
        strategy = FIFOBasisStrategy()
        logger.debug("Using FIFO strategy for cost basis calculation.")

    disposition_engine = LotDispositionEngine(cost_basis_strategy=strategy)
    return CostBasisTimelineProcessor(
        parser=CostTransactionParser(error_reporter=error_reporter),
        sorter=CostTransactionSorter(),
        disposition_engine=disposition_engine,
        cost_calculator=CostBasisCalculator(
            disposition_engine=disposition_engine,
            error_reporter=error_reporter,
        ),
        error_reporter=error_reporter,
        observer=observer,
    )


class CostBasisTimelineProcessor:
    """Coordinate parsing, ordering, cost calculation, and resulting open-lot state."""

    def __init__(
        self,
        parser: CostTransactionParser,
        sorter: CostTransactionSorter,
        disposition_engine: LotDispositionEngine,
        cost_calculator: CostBasisCalculator,
        error_reporter: CostCalculationErrorCollector,
        observer: CostBasisCalculationObserver | None = None,
    ) -> None:
        self._parser = parser
        self._sorter = sorter
        self._disposition_engine = disposition_engine
        self._cost_calculator = cost_calculator
        self._error_reporter = error_reporter
        self._observer = observer or _NullCostBasisCalculationObserver()

    def process_transactions(
        self,
        existing_transactions_raw: list[dict[str, Any]],
        new_transactions_raw: list[dict[str, Any]],
    ) -> tuple[list[CostBasisTransaction], list[CostCalculationError], dict[str, OpenLotState]]:
        with self._observer.observe_recalculation() as observation:
            self._error_reporter.clear()

            parsed_existing = self._parser.parse_transactions(existing_transactions_raw)
            parsed_new = self._parser.parse_transactions(new_transactions_raw)
            new_transaction_ids = self._valid_transaction_ids(parsed_new)
            all_valid_transactions = self._valid_transactions(parsed_existing, parsed_new)

            observation.record_depth(len(all_valid_transactions))
            sorted_timeline = self._sorter.sort_transactions([], all_valid_transactions)
            processed_timeline = self._process_sorted_timeline(sorted_timeline)
            final_processed_new = self._filter_processed_new_transactions(
                processed_timeline=processed_timeline,
                new_transaction_ids=new_transaction_ids,
            )

            return (
                final_processed_new,
                self._error_reporter.get_errors(),
                self._disposition_engine.get_open_lot_states(),
            )

    def process_increment(
        self,
        *,
        initial_open_lots_raw: list[dict[str, Any]],
        new_transactions_raw: list[dict[str, Any]],
    ) -> tuple[list[CostBasisTransaction], list[CostCalculationError], dict[str, OpenLotState]]:
        """Calculate an ordered append from a previously validated open-lot checkpoint."""
        with self._observer.observe_recalculation() as observation:
            self._error_reporter.clear()
            parsed_initial_lots = self._parser.parse_transactions(initial_open_lots_raw)
            parsed_new = self._parser.parse_transactions(new_transactions_raw)
            valid_initial_lots = [txn for txn in parsed_initial_lots if not txn.error_reason]
            valid_new = [txn for txn in parsed_new if not txn.error_reason]

            observation.record_depth(len(valid_new))
            sorted_initial_lots = self._sorter.sort_transactions([], valid_initial_lots)
            self._disposition_engine.restore_open_lots(sorted_initial_lots)
            sorted_new = self._sorter.sort_transactions([], valid_new)
            processed_new = self._process_sorted_timeline(sorted_new)
            return (
                processed_new,
                self._error_reporter.get_errors(),
                self._disposition_engine.get_open_lot_states(),
            )

    @staticmethod
    def _valid_transaction_ids(transactions: list[CostBasisTransaction]) -> set[str]:
        return {txn.transaction_id for txn in transactions if not txn.error_reason}

    @staticmethod
    def _valid_transactions(
        parsed_existing: list[CostBasisTransaction],
        parsed_new: list[CostBasisTransaction],
    ) -> list[CostBasisTransaction]:
        return [txn for txn in [*parsed_existing, *parsed_new] if not txn.error_reason]

    @staticmethod
    def _filter_processed_new_transactions(
        *,
        processed_timeline: list[CostBasisTransaction],
        new_transaction_ids: set[str],
    ) -> list[CostBasisTransaction]:
        return [txn for txn in processed_timeline if txn.transaction_id in new_transaction_ids]

    def _process_sorted_timeline(
        self, sorted_timeline: list[CostBasisTransaction]
    ) -> list[CostBasisTransaction]:
        processed_timeline: list[CostBasisTransaction] = []
        for transaction in sorted_timeline:
            if self._calculate_transaction_costs(transaction):
                processed_timeline.append(transaction)
        return processed_timeline

    def _calculate_transaction_costs(self, transaction: CostBasisTransaction) -> bool:
        try:
            self._cost_calculator.calculate_transaction_costs(transaction)
        except Exception as exc:
            self._record_unexpected_processing_error(transaction, exc)
            return False
        return not self._error_reporter.has_errors_for(transaction.transaction_id)

    def _record_unexpected_processing_error(
        self, transaction: CostBasisTransaction, exc: Exception
    ) -> None:
        logger.error(
            "Unexpected error for transaction %s: %s",
            transaction.transaction_id,
            exc,
            exc_info=True,
        )
        self._error_reporter.add_error(transaction.transaction_id, f"Unexpected error: {str(exc)}")


class _NullCostBasisCalculationObservation(CostBasisCalculationObservation):
    def record_depth(self, transaction_count: int) -> None:
        del transaction_count

    def __enter__(self) -> _NullCostBasisCalculationObservation:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None


class _NullCostBasisCalculationObserver(CostBasisCalculationObserver):
    def observe_recalculation(self) -> CostBasisCalculationObservation:
        return _NullCostBasisCalculationObservation()
