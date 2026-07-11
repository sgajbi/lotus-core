"""Read and continuation ports for transaction-economics source products."""

from datetime import date
from typing import Any, Protocol

from ..domain.transaction_economics import BookedTransactionEconomics

TransactionCostCurveKey = tuple[str, str, str]
TransactionEconomicsPageKey = tuple[str, str, str]


class TransactionEconomicsReader(Protocol):
    """Read source-authored transaction economics without exposing persistence models."""

    async def portfolio_exists(self, portfolio_id: str) -> bool: ...

    async def get_portfolio_base_currency(self, portfolio_id: str) -> str | None: ...

    async def list_transaction_cost_curve_keys(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None,
        transaction_types: list[str] | None,
        min_observation_count: int,
        after_key: TransactionCostCurveKey | tuple[()],
        limit: int,
    ) -> list[TransactionCostCurveKey]: ...

    async def list_transaction_cost_curve_available_security_ids(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None,
        transaction_types: list[str] | None,
        min_observation_count: int,
    ) -> set[str]: ...

    async def list_transaction_cost_evidence(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None,
        transaction_types: list[str] | None,
        curve_keys: list[TransactionCostCurveKey] | None,
    ) -> list[BookedTransactionEconomics]: ...

    async def list_performance_component_economics_evidence(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        as_of_date: date,
        security_ids: list[str] | None,
        transaction_types: list[str] | None,
        after_key: TransactionEconomicsPageKey | tuple[()],
        limit: int | None,
    ) -> list[BookedTransactionEconomics]: ...


class TransactionEconomicsPageTokenCodec(Protocol):
    """Encode and decode opaque continuation state for economics evidence pages."""

    def encode(self, payload: dict[str, Any]) -> str: ...

    def decode(self, token: str | None) -> dict[str, Any]: ...
