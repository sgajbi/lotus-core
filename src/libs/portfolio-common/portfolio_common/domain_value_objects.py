from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from portfolio_common.currency_codes import normalize_currency_code
from portfolio_common.decimal_amounts import decimal_or_none, required_decimal

DEFAULT_MONEY_QUANTUM = Decimal("0.01")


class CurrencyBasis(StrEnum):
    BOOK = "book"
    TRADE = "trade"
    LOCAL = "local"
    BASE = "base"
    REPORTING = "reporting"


@dataclass(frozen=True, slots=True)
class CurrencyCode:
    value: str

    @classmethod
    def from_raw(cls, currency: object) -> CurrencyCode:
        return cls(normalize_currency_code(currency))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MoneyAmount:
    amount: Decimal
    currency: CurrencyCode

    @classmethod
    def from_raw(cls, *, amount: object, currency: object) -> MoneyAmount:
        return cls(
            amount=required_decimal(amount, field_name="amount"),
            currency=CurrencyCode.from_raw(currency),
        )

    @classmethod
    def optional_from_raw(cls, *, amount: object, currency: object) -> MoneyAmount | None:
        resolved_amount = decimal_or_none(amount)
        if resolved_amount is None:
            return None
        return cls(amount=resolved_amount, currency=CurrencyCode.from_raw(currency))

    def quantized(self, quantum: Decimal = DEFAULT_MONEY_QUANTUM) -> MoneyAmount:
        return MoneyAmount(
            amount=self.amount.quantize(quantum, rounding=ROUND_HALF_UP),
            currency=self.currency,
        )

    def converted(self, rate: FxRate) -> MoneyAmount:
        if self.currency != rate.from_currency:
            raise ValueError(
                "FX source currency mismatch: "
                f"money={self.currency.value}, rate={rate.from_currency.value}"
            )
        return MoneyAmount(
            amount=self.amount * rate.rate,
            currency=rate.to_currency,
        )

    def as_boundary_payload(self) -> dict[str, str]:
        return {"amount": str(self.amount), "currency": self.currency.value}


@dataclass(frozen=True, slots=True)
class FxRate:
    from_currency: CurrencyCode
    to_currency: CurrencyCode
    rate: Decimal
    as_of_date: date | None = None

    @classmethod
    def from_raw(
        cls,
        *,
        from_currency: object,
        to_currency: object,
        rate: object,
        as_of_date: date | None = None,
    ) -> FxRate:
        resolved_rate = required_decimal(rate, field_name="fx_rate")
        if resolved_rate <= Decimal("0"):
            raise ValueError("fx_rate must be positive")
        return cls(
            from_currency=CurrencyCode.from_raw(from_currency),
            to_currency=CurrencyCode.from_raw(to_currency),
            rate=resolved_rate,
            as_of_date=as_of_date,
        )

    @classmethod
    def identity(cls, *, currency: object, as_of_date: date | None = None) -> FxRate:
        normalized_currency = CurrencyCode.from_raw(currency)
        return cls(
            from_currency=normalized_currency,
            to_currency=normalized_currency,
            rate=Decimal("1"),
            as_of_date=as_of_date,
        )

    @classmethod
    def for_pair(
        cls,
        *,
        from_currency: object,
        to_currency: object,
        rate: object,
        as_of_date: date | None = None,
    ) -> FxRate:
        normalized_from_currency = CurrencyCode.from_raw(from_currency)
        normalized_to_currency = CurrencyCode.from_raw(to_currency)
        if normalized_from_currency == normalized_to_currency:
            return cls.identity(currency=normalized_from_currency.value, as_of_date=as_of_date)
        return cls.from_raw(
            from_currency=normalized_from_currency.value,
            to_currency=normalized_to_currency.value,
            rate=rate,
            as_of_date=as_of_date,
        )


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal

    @classmethod
    def from_raw(cls, quantity: object) -> Quantity:
        return cls(required_decimal(quantity, field_name="quantity"))


@dataclass(frozen=True, slots=True)
class UnitPrice:
    value: Decimal
    currency: CurrencyCode | None = None

    @classmethod
    def from_raw(cls, *, price: object, currency: object | None = None) -> UnitPrice:
        normalized_currency = CurrencyCode.from_raw(currency) if currency is not None else None
        return cls(
            value=required_decimal(price, field_name="unit_price"),
            currency=normalized_currency,
        )

    def as_boundary_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"price": str(self.value)}
        if self.currency is not None:
            payload["currency"] = self.currency.value
        return payload


BookCost = MoneyAmount
MarketValue = MoneyAmount
AccruedIncome = MoneyAmount
WithholdingTaxAmount = MoneyAmount
RealizedPnL = MoneyAmount
