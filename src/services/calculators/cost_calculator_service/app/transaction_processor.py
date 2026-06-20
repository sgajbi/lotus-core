import logging
import time
from decimal import Decimal
from typing import Any

from .cost_engine.domain.models.error import ErroredTransaction
from .cost_engine.domain.models.transaction import Transaction
from .cost_engine.processing.cost_calculator import CostCalculator
from .cost_engine.processing.disposition_engine import DispositionEngine
from .cost_engine.processing.error_reporter import ErrorReporter
from .cost_engine.processing.parser import TransactionParser
from .cost_engine.processing.sorter import TransactionSorter
from .monitoring import RECALCULATION_DEPTH, RECALCULATION_DURATION_SECONDS

logger = logging.getLogger(__name__)


class TransactionProcessor:
    """
    Orchestrates end-to-end transaction recalculation for the cost calculator service.

    This layer orchestrates the service-owned cost-basis engine.
    """

    def __init__(
        self,
        parser: TransactionParser,
        sorter: TransactionSorter,
        disposition_engine: DispositionEngine,
        cost_calculator: CostCalculator,
        error_reporter: ErrorReporter,
    ):
        self._parser = parser
        self._sorter = sorter
        self._disposition_engine = disposition_engine
        self._cost_calculator = cost_calculator
        self._error_reporter = error_reporter

    def process_transactions(
        self,
        existing_transactions_raw: list[dict[str, Any]],
        new_transactions_raw: list[dict[str, Any]],
    ) -> tuple[list[Transaction], list[ErroredTransaction], dict[str, Decimal]]:
        start_time = time.monotonic()
        try:
            self._error_reporter.clear()

            parsed_existing = self._parser.parse_transactions(existing_transactions_raw)
            parsed_new = self._parser.parse_transactions(new_transactions_raw)
            new_transaction_ids = self._valid_transaction_ids(parsed_new)
            all_valid_transactions = self._valid_transactions(parsed_existing, parsed_new)

            RECALCULATION_DEPTH.observe(len(all_valid_transactions))
            sorted_timeline = self._sorter.sort_transactions([], all_valid_transactions)
            processed_timeline = self._process_sorted_timeline(sorted_timeline)
            final_processed_new = self._filter_processed_new_transactions(
                processed_timeline=processed_timeline,
                new_transaction_ids=new_transaction_ids,
            )

            return (
                final_processed_new,
                self._error_reporter.get_errors(),
                self._disposition_engine.get_open_lot_quantities(),
            )
        finally:
            duration = time.monotonic() - start_time
            RECALCULATION_DURATION_SECONDS.observe(duration)

    @staticmethod
    def _valid_transaction_ids(transactions: list[Transaction]) -> set[str]:
        return {txn.transaction_id for txn in transactions if not txn.error_reason}

    @staticmethod
    def _valid_transactions(
        parsed_existing: list[Transaction],
        parsed_new: list[Transaction],
    ) -> list[Transaction]:
        return [txn for txn in [*parsed_existing, *parsed_new] if not txn.error_reason]

    @staticmethod
    def _filter_processed_new_transactions(
        *,
        processed_timeline: list[Transaction],
        new_transaction_ids: set[str],
    ) -> list[Transaction]:
        return [txn for txn in processed_timeline if txn.transaction_id in new_transaction_ids]

    def _process_sorted_timeline(self, sorted_timeline: list[Transaction]) -> list[Transaction]:
        processed_timeline: list[Transaction] = []
        for transaction in sorted_timeline:
            if self._calculate_transaction_costs(transaction):
                processed_timeline.append(transaction)
        return processed_timeline

    def _calculate_transaction_costs(self, transaction: Transaction) -> bool:
        try:
            self._cost_calculator.calculate_transaction_costs(transaction)
        except Exception as exc:
            self._record_unexpected_processing_error(transaction, exc)
            return False
        return not self._error_reporter.has_errors_for(transaction.transaction_id)

    def _record_unexpected_processing_error(self, transaction: Transaction, exc: Exception) -> None:
        logger.error(
            "Unexpected error for transaction %s: %s",
            transaction.transaction_id,
            exc,
            exc_info=True,
        )
        self._error_reporter.add_error(transaction.transaction_id, f"Unexpected error: {str(exc)}")
