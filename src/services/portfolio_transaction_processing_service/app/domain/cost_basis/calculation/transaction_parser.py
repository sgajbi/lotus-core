"""Map raw ledger records into validated cost-basis transactions."""

import logging
from decimal import Decimal
from typing import Any

from ..models.cost_basis_transaction import CostBasisTransaction
from .calculation_errors import CostCalculationErrorCollector

logger = logging.getLogger(__name__)


class CostTransactionParser:
    """
    Parses raw transaction dictionaries into validated CostBasisTransaction objects.
    """

    def __init__(self, error_reporter: CostCalculationErrorCollector):
        self._error_reporter = error_reporter

    def parse_transactions(
        self, raw_transaction_data: list[dict[str, Any]]
    ) -> list[CostBasisTransaction]:
        parsed_transactions: list[CostBasisTransaction] = []
        for raw_txn_data in raw_transaction_data:
            transaction_id = raw_txn_data.get("transaction_id", "UNKNOWN_ID_BEFORE_PARSE")
            try:
                validated_txn = CostBasisTransaction(**raw_txn_data)
                parsed_transactions.append(validated_txn)
            except (TypeError, ValueError) as e:
                error_reason = f"Validation error: {str(e)}"
                self._error_reporter.add_error(transaction_id, error_reason)
                stub_txn = self._create_stub_transaction(raw_txn_data, error_reason)
                parsed_transactions.append(stub_txn)
            except Exception as e:
                error_reason = f"Unexpected parsing error: {type(e).__name__}: {str(e)}"
                self._error_reporter.add_error(transaction_id, error_reason)
                stub_txn = self._create_stub_transaction(raw_txn_data, error_reason)
                parsed_transactions.append(stub_txn)
        return parsed_transactions

    def _create_stub_transaction(self, raw_data: dict, error_reason: str) -> CostBasisTransaction:
        """Creates a minimal CostBasisTransaction object to hold error information."""
        return CostBasisTransaction(
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
            portfolio_base_currency=raw_data.get("portfolio_base_currency", "UNK"),
            error_reason=error_reason,
        )
