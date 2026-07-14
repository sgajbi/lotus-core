"""Define the read-only source contract for canonical FX transaction values."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class FxTransactionSource(Protocol):
    """Expose the required inputs for canonical FX transaction economics."""

    @property
    def transaction_id(self) -> str: ...

    @property
    def transaction_type(self) -> str: ...

    @property
    def component_type(self) -> str | None: ...

    @property
    def component_id(self) -> str | None: ...

    @property
    def linked_component_ids(self) -> tuple[str, ...] | list[str] | None: ...

    @property
    def portfolio_id(self) -> str: ...

    @property
    def instrument_id(self) -> str: ...

    @property
    def security_id(self) -> str: ...

    @property
    def transaction_date(self) -> datetime: ...

    @property
    def settlement_date(self) -> datetime | None: ...

    @property
    def quantity(self) -> Decimal: ...

    @property
    def price(self) -> Decimal: ...

    @property
    def gross_transaction_amount(self) -> Decimal: ...

    @property
    def trade_currency(self) -> str: ...

    @property
    def currency(self) -> str: ...

    @property
    def pair_base_currency(self) -> str | None: ...

    @property
    def pair_quote_currency(self) -> str | None: ...

    @property
    def fx_rate_quote_convention(self) -> str | None: ...

    @property
    def buy_currency(self) -> str | None: ...

    @property
    def sell_currency(self) -> str | None: ...

    @property
    def buy_amount(self) -> Decimal | None: ...

    @property
    def sell_amount(self) -> Decimal | None: ...

    @property
    def contract_rate(self) -> Decimal | None: ...
