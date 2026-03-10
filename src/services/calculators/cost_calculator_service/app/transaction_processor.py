import logging
import time
from typing import Any

from core.models.response import ErroredTransaction
from core.models.transaction import Transaction
from logic.cost_calculator import CostCalculator
from logic.disposition_engine import DispositionEngine
from logic.error_reporter import ErrorReporter
from logic.parser import TransactionParser
from logic.sorter import TransactionSorter

from .monitoring import RECALCULATION_DEPTH, RECALCULATION_DURATION_SECONDS

logger = logging.getLogger(__name__)


class TransactionProcessor:
    """
    Orchestrates end-to-end transaction recalculation for the cost calculator service.

    This layer is service-owned orchestration around the shared cost-basis domain logic.
    The reusable engine remains in `financial-calculator-engine/src/{core,logic}`.
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
    ) -> tuple[list[Transaction], list[ErroredTransaction]]:
        start_time = time.monotonic()
        try:
            self._error_reporter.clear()

            parsed_existing = self._parser.parse_transactions(existing_transactions_raw)
            parsed_new = self._parser.parse_transactions(new_transactions_raw)
            new_transaction_ids = {txn.transaction_id for txn in parsed_new if not txn.error_reason}

            all_valid_transactions = [txn for txn in parsed_existing if not txn.error_reason] + [
                txn for txn in parsed_new if not txn.error_reason
            ]

            RECALCULATION_DEPTH.observe(len(all_valid_transactions))
            sorted_timeline = self._sorter.sort_transactions([], all_valid_transactions)

            processed_timeline: list[Transaction] = []
            for transaction in sorted_timeline:
                try:
                    self._cost_calculator.calculate_transaction_costs(transaction)

                    if not self._error_reporter.has_errors_for(transaction.transaction_id):
                        processed_timeline.append(transaction)
                except Exception as exc:
                    logger.error(
                        "Unexpected error for transaction %s: %s",
                        transaction.transaction_id,
                        exc,
                        exc_info=True,
                    )
                    self._error_reporter.add_error(
                        transaction.transaction_id, f"Unexpected error: {str(exc)}"
                    )

            final_processed_new = [
                txn for txn in processed_timeline if txn.transaction_id in new_transaction_ids
            ]

            return final_processed_new, self._error_reporter.get_errors()
        finally:
            duration = time.monotonic() - start_time
            RECALCULATION_DURATION_SECONDS.observe(duration)
