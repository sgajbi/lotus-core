from dataclasses import dataclass


@dataclass
class ErroredTransaction:
    """
    Represents a transaction that failed processing, along with the reason for failure.
    """

    transaction_id: str
    error_reason: str
