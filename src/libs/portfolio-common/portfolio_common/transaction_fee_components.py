from decimal import Decimal
from typing import Mapping

from portfolio_common.decimal_amounts import decimal_or_none

TRANSACTION_FEE_COMPONENT_FIELDS = (
    "brokerage",
    "stamp_duty",
    "exchange_fee",
    "gst",
    "other_fees",
)
ZERO = Decimal("0")


def _is_blank(value: object) -> bool:
    return isinstance(value, str) and not value.strip()


def _optional_fee_amount(value: object, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    normalized_amount = decimal_or_none(value)
    if normalized_amount is None:
        raise ValueError(f"{field_name} must be numeric.")
    return normalized_amount


def _fee_component_amount(value: object, *, field_name: str) -> Decimal:
    if value is None or _is_blank(value):
        return ZERO
    normalized_amount = decimal_or_none(value)
    if normalized_amount is None:
        raise ValueError(f"{field_name} must be numeric.")
    return normalized_amount


def resolve_transaction_trade_fee(
    trade_fee: Decimal | None,
    fee_components: Mapping[str, object],
) -> Decimal | None:
    if trade_fee is not None:
        normalized_trade_fee = _optional_fee_amount(trade_fee, field_name="trade_fee")
        if normalized_trade_fee < 0:
            raise ValueError("trade_fee must be greater than or equal to zero.")
    else:
        normalized_trade_fee = None

    if not any(value is not None for value in fee_components.values()):
        return normalized_trade_fee

    normalized_components: list[Decimal] = []
    for field_name, value in fee_components.items():
        amount = _fee_component_amount(value, field_name=field_name)
        if amount < 0:
            raise ValueError(f"{field_name} must be greater than or equal to zero.")
        normalized_components.append(amount)
    return sum(normalized_components)
