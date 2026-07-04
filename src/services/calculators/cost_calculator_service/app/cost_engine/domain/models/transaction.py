from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _iso_datetime_text(value: str) -> str:
    if value.endswith("Z"):
        return value[:-1] + "+00:00"
    return value


def _parse_datetime_text(value: str) -> datetime:
    return datetime.fromisoformat(_iso_datetime_text(value))


def _utc_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def standardize_datetime_value(value: Any) -> Any:
    if value is None:
        return value
    if isinstance(value, str):
        return _utc_aware_datetime(_parse_datetime_text(value))
    if isinstance(value, datetime):
        return _utc_aware_datetime(value)
    return value


def _required_text(value: object, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    if isinstance(value, str):
        return value
    return str(value)


def _decimal_value(value: object, *, field_name: str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal") from exc


def _optional_decimal(value: object, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal_value(value, field_name=field_name)


def _non_negative(value: object, *, field_name: str) -> Decimal:
    amount = _decimal_value(value, field_name=field_name)
    if amount < Decimal("0"):
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return amount


def _optional_non_negative(value: object, *, field_name: str) -> Decimal | None:
    amount = _optional_decimal(value, field_name=field_name)
    if amount is not None and amount < Decimal("0"):
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return amount


def _optional_positive(value: object, *, field_name: str) -> Decimal | None:
    amount = _optional_decimal(value, field_name=field_name)
    if amount is not None and amount <= Decimal("0"):
        raise ValueError(f"{field_name} must be greater than 0")
    return amount


def _model_dump(
    instance: object, *, exclude_none: bool, exclude: set[str] | None
) -> dict[str, Any]:
    excluded_fields = exclude or set()
    payload: dict[str, Any] = {}
    for field in fields(instance):
        if field.name == "_extra_fields" or field.name in excluded_fields:
            continue
        value = getattr(instance, field.name)
        if exclude_none and value is None:
            continue
        if hasattr(value, "model_dump"):
            value = value.model_dump(exclude_none=exclude_none)
        payload[field.name] = value
    for field_name, value in getattr(instance, "_extra_fields", {}).items():
        if field_name in excluded_fields or (exclude_none and value is None):
            continue
        payload[field_name] = value
    return payload


@dataclass(init=False)
class Fees:
    """
    Represents various fees associated with a transaction.
    """

    stamp_duty: Decimal
    exchange_fee: Decimal
    gst: Decimal
    brokerage: Decimal
    other_fees: Decimal

    def __init__(
        self,
        *,
        stamp_duty: object = Decimal(0),
        exchange_fee: object = Decimal(0),
        gst: object = Decimal(0),
        brokerage: object = Decimal(0),
        other_fees: object = Decimal(0),
    ) -> None:
        self.stamp_duty = _non_negative(stamp_duty, field_name="stamp_duty")
        self.exchange_fee = _non_negative(exchange_fee, field_name="exchange_fee")
        self.gst = _non_negative(gst, field_name="gst")
        self.brokerage = _non_negative(brokerage, field_name="brokerage")
        self.other_fees = _non_negative(other_fees, field_name="other_fees")

    @property
    def total_fees(self) -> Decimal:
        """Calculates the sum of all fees."""
        return self.stamp_duty + self.exchange_fee + self.gst + self.brokerage + self.other_fees

    def model_dump(
        self,
        *,
        exclude_none: bool = False,
        exclude: set[str] | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        del mode
        return _model_dump(self, exclude_none=exclude_none, exclude=exclude)


@dataclass(init=False)
class Transaction:
    """
    Represents a single financial transaction.
    """

    transaction_id: str
    portfolio_id: str
    instrument_id: str
    security_id: str
    transaction_type: str
    transaction_date: datetime
    settlement_date: datetime | None
    quantity: Decimal
    gross_transaction_amount: Decimal
    net_transaction_amount: Decimal | None
    fees: Fees | None
    accrued_interest: Decimal | None
    average_price: Decimal | None
    trade_currency: str
    portfolio_base_currency: str
    transaction_fx_rate: Decimal | None
    net_cost: Decimal | None
    gross_cost: Decimal | None
    realized_gain_loss: Decimal | None
    net_cost_local: Decimal | None
    realized_gain_loss_local: Decimal | None
    error_reason: str | None
    _extra_fields: dict[str, Any]

    def __init__(
        self,
        *,
        transaction_id: object,
        portfolio_id: object,
        instrument_id: object,
        security_id: object,
        transaction_type: object,
        transaction_date: object,
        quantity: object,
        gross_transaction_amount: object,
        trade_currency: object,
        portfolio_base_currency: object,
        settlement_date: object = None,
        net_transaction_amount: object = None,
        fees: Fees | dict[str, object] | None = None,
        accrued_interest: object = Decimal(0),
        average_price: object = None,
        transaction_fx_rate: object = None,
        net_cost: object = None,
        gross_cost: object = None,
        realized_gain_loss: object = None,
        net_cost_local: object = None,
        realized_gain_loss_local: object = None,
        error_reason: object = None,
        **extra_fields: Any,
    ) -> None:
        self.transaction_id = _required_text(transaction_id, field_name="transaction_id")
        self.portfolio_id = _required_text(portfolio_id, field_name="portfolio_id")
        self.instrument_id = _required_text(instrument_id, field_name="instrument_id")
        self.security_id = _required_text(security_id, field_name="security_id")
        self.transaction_type = _required_text(transaction_type, field_name="transaction_type")
        self.transaction_date = standardize_datetime_value(transaction_date)
        if not isinstance(self.transaction_date, datetime):
            raise ValueError("transaction_date must be a datetime")
        self.settlement_date = standardize_datetime_value(settlement_date)
        if self.settlement_date is not None and not isinstance(self.settlement_date, datetime):
            raise ValueError("settlement_date must be a datetime")
        self.quantity = _non_negative(quantity, field_name="quantity")
        self.gross_transaction_amount = _non_negative(
            gross_transaction_amount,
            field_name="gross_transaction_amount",
        )
        self.net_transaction_amount = _optional_non_negative(
            net_transaction_amount,
            field_name="net_transaction_amount",
        )
        if fees is None:
            self.fees = Fees()
        elif isinstance(fees, Fees):
            self.fees = fees
        else:
            self.fees = Fees(**fees)
        self.accrued_interest = _optional_non_negative(
            accrued_interest,
            field_name="accrued_interest",
        )
        self.average_price = _optional_non_negative(average_price, field_name="average_price")
        self.trade_currency = _required_text(trade_currency, field_name="trade_currency")
        self.portfolio_base_currency = _required_text(
            portfolio_base_currency,
            field_name="portfolio_base_currency",
        )
        self.transaction_fx_rate = _optional_positive(
            transaction_fx_rate,
            field_name="transaction_fx_rate",
        )
        self.net_cost = _optional_decimal(net_cost, field_name="net_cost")
        self.gross_cost = _optional_decimal(gross_cost, field_name="gross_cost")
        self.realized_gain_loss = _optional_decimal(
            realized_gain_loss,
            field_name="realized_gain_loss",
        )
        self.net_cost_local = _optional_decimal(net_cost_local, field_name="net_cost_local")
        self.realized_gain_loss_local = _optional_decimal(
            realized_gain_loss_local,
            field_name="realized_gain_loss_local",
        )
        self.error_reason = str(error_reason) if error_reason is not None else None
        self._extra_fields = dict(extra_fields)
        for field_name, value in self._extra_fields.items():
            setattr(self, field_name, value)

    def model_copy(self, *, update: dict[str, Any] | None = None) -> Transaction:
        copied = object.__new__(Transaction)
        for field_name, value in vars(self).items():
            setattr(copied, field_name, value)
        copied._extra_fields = dict(self._extra_fields)
        if update:
            for field_name, value in update.items():
                setattr(copied, field_name, value)
                if field_name not in {field.name for field in fields(Transaction)}:
                    copied._extra_fields[field_name] = value
        return copied

    def model_dump(
        self,
        *,
        exclude_none: bool = False,
        exclude: set[str] | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        del mode
        return _model_dump(self, exclude_none=exclude_none, exclude=exclude)
