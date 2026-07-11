"""Represent a transaction-level cost-calculation validation error."""

from dataclasses import dataclass


@dataclass
class CostCalculationError:
    """
    Represents a transaction that failed processing, along with the reason for failure.
    """

    transaction_id: str
    error_reason: str
