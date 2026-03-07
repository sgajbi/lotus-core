# src/core/enums/transaction_type.py

from enum import Enum


class TransactionType(str, Enum):
    """
    Defines the supported types of financial transactions.
    Inheriting from 'str' ensures that the enum values are strings,
    making them directly usable and comparable with string inputs.
    """

    BUY = "BUY"
    SELL = "SELL"
    INTEREST = "INTEREST"
    DIVIDEND = "DIVIDEND"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    FEE = "FEE"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    MERGER_OUT = "MERGER_OUT"
    MERGER_IN = "MERGER_IN"
    EXCHANGE_OUT = "EXCHANGE_OUT"
    EXCHANGE_IN = "EXCHANGE_IN"
    REPLACEMENT_OUT = "REPLACEMENT_OUT"
    REPLACEMENT_IN = "REPLACEMENT_IN"
    CASH_IN_LIEU = "CASH_IN_LIEU"
    ADJUSTMENT = "ADJUSTMENT"
    OTHER = "OTHER"  # Catch-all for any other transaction types not explicitly defined

    @classmethod
    def list(cls):
        """Returns a list of all transaction type values."""
        return list(map(lambda c: c.value, cls))

    @classmethod
    def is_valid(cls, transaction_type_str: str) -> bool:
        """Checks if a given string is a valid transaction type."""
        return transaction_type_str in cls.list()
