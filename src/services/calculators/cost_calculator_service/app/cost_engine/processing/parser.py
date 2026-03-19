import logging
from decimal import Decimal
from typing import Any

from pydantic import TypeAdapter, ValidationError

from ..domain.models.transaction import Transaction
from .error_reporter import ErrorReporter

logger = logging.getLogger(__name__)


class TransactionParser:
    """
    Parses raw transaction dictionaries into validated Transaction objects.
    """

    def __init__(self, error_reporter: ErrorReporter):
        self._single_transaction_adapter = TypeAdapter(Transaction)
        self._error_reporter = error_reporter

    def parse_transactions(self, raw_transaction_data: list[dict[str, Any]]) -> list[Transaction]:
        parsed_transactions: list[Transaction] = []
        for raw_txn_data in raw_transaction_data:
            transaction_id = raw_txn_data.get("transaction_id", "UNKNOWN_ID_BEFORE_PARSE")
            try:
                validated_txn = self._single_transaction_adapter.validate_python(raw_txn_data)
                parsed_transactions.append(validated_txn)
            except ValidationError as e:
                error_messages = "; ".join(
                    [f"{err.get('loc', ['unknown'])[0]}: {err['msg']}" for err in e.errors()]
                )
                error_reason = f"Validation error: {error_messages}"
                self._error_reporter.add_error(transaction_id, error_reason)
                stub_txn = self._create_stub_transaction(raw_txn_data, error_reason)
                parsed_transactions.append(stub_txn)
            except Exception as e:
                error_reason = f"Unexpected parsing error: {type(e).__name__}: {str(e)}"
                self._error_reporter.add_error(transaction_id, error_reason)
                stub_txn = self._create_stub_transaction(raw_txn_data, error_reason)
                parsed_transactions.append(stub_txn)
        return parsed_transactions

    def _create_stub_transaction(self, raw_data: dict, error_reason: str) -> Transaction:
        """Creates a minimal Transaction object to hold error information."""
        return Transaction(
            transaction_id=raw_data.get("transaction_id", "UNKNOWN_ID"),
            portfolio_id=raw_data.get("portfolio_id", "UNKNOWN"),
            instrument_id=raw_data.get("instrument_id", "UNKNOWN"),
            security_id=raw_data.get("security_id", "UNKNOWN"),
            transaction_type=raw_data.get("transaction_type", "UNKNOWN"),
            transaction_date=raw_data.get("transaction_date", "1970-01-01"),
            settlement_date=raw_data.get("settlement_date", "1970-01-01"),
            quantity=raw_data.get("quantity", Decimal(0)),
            gross_transaction_amount=raw_data.get("gross_transaction_amount", Decimal(0)),
            trade_currency=raw_data.get("trade_currency", "UNK"),
            # --- FIX: Add required field with a sensible default ---
            portfolio_base_currency=raw_data.get("portfolio_base_currency", "UNK"),
            error_reason=error_reason,
        )
