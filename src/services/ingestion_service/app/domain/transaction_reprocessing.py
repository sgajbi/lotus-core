"""Domain identities required to order transaction reprocessing safely."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TransactionReprocessingTarget:
    """Source-owned transaction and portfolio identity for one repair command."""

    transaction_id: str
    portfolio_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transaction_id",
            _required_identity(self.transaction_id, field_name="transaction_id"),
        )
        object.__setattr__(
            self,
            "portfolio_id",
            _required_identity(self.portfolio_id, field_name="portfolio_id"),
        )


def _required_identity(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized
