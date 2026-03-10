# libs/financial-calculator-engine/src/logic/error_reporter.py
from core.models.error import ErroredTransaction


class ErrorReporter:
    """
    Manages the collection and reporting of processing errors for transactions.
    """

    def __init__(self):
        self._errored_transactions: dict[str, ErroredTransaction] = {}

    def add_error(self, transaction_id: str, error_reason: str):
        if transaction_id in self._errored_transactions:
            existing_reason = self._errored_transactions[transaction_id].error_reason
            if error_reason not in existing_reason:
                self._errored_transactions[transaction_id].error_reason += f"; {error_reason}"
        else:
            self._errored_transactions[transaction_id] = ErroredTransaction(
                transaction_id=transaction_id, error_reason=error_reason
            )

    def get_errors(self) -> list[ErroredTransaction]:
        return list(self._errored_transactions.values())

    def has_errors(self) -> bool:
        return bool(self._errored_transactions)

    def has_errors_for(self, transaction_id: str) -> bool:
        return transaction_id in self._errored_transactions

    def clear(self):
        self._errored_transactions = {}
