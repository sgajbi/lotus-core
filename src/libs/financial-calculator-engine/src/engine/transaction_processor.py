# libs/financial-calculator-engine/src/engine/transaction_processor.py
import logging
import time
from typing import Any, Tuple

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
    Orchestrates the end-to-end processing of financial transactions by
    recalculating a full history to ensure correctness and idempotency.
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
    ) -> Tuple[list[Transaction], list[ErroredTransaction]]:
        start_time = time.monotonic()
        try:
            self._error_reporter.clear()

            # 1. Parse all transactions
            parsed_existing = self._parser.parse_transactions(existing_transactions_raw)
            parsed_new = self._parser.parse_transactions(new_transactions_raw)
            new_transaction_ids = {txn.transaction_id for txn in parsed_new if not txn.error_reason}

            # 2. Combine and sort the full, valid transaction history
            all_valid_transactions = [txn for txn in parsed_existing if not txn.error_reason] + [
                txn for txn in parsed_new if not txn.error_reason
            ]

            # Observe the depth of the recalculation
            RECALCULATION_DEPTH.observe(len(all_valid_transactions))

            sorted_timeline = self._sorter.sort_transactions([], all_valid_transactions)

            # 3. Process the entire timeline from scratch
            processed_timeline: list[Transaction] = []
            for transaction in sorted_timeline:
                try:
                    # Calculate costs for every transaction in the timeline
                    self._cost_calculator.calculate_transaction_costs(transaction)

                    if not self._error_reporter.has_errors_for(transaction.transaction_id):
                        processed_timeline.append(transaction)
                except Exception as e:
                    logger.error(
                        f"Unexpected error for transaction {transaction.transaction_id}: {e}",
                        exc_info=True,
                    )
                    self._error_reporter.add_error(
                        transaction.transaction_id, f"Unexpected error: {str(e)}"
                    )

            # 4. Filter results to return only the newly processed transactions
            final_processed_new = [
                txn for txn in processed_timeline if txn.transaction_id in new_transaction_ids
            ]

            return final_processed_new, self._error_reporter.get_errors()
        finally:
            duration = time.monotonic() - start_time
            RECALCULATION_DURATION_SECONDS.observe(duration)
