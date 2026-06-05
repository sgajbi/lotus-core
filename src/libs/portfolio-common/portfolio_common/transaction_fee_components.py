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
    normalized_trade_fee = _validated_optional_fee_amount(trade_fee, field_name="trade_fee")
    if not _has_fee_components(fee_components):
        return normalized_trade_fee
    return _total_fee_component_amount(fee_components)


def _validated_optional_fee_amount(value: object, *, field_name: str) -> Decimal | None:
    normalized_amount = _optional_fee_amount(value, field_name=field_name)
    if normalized_amount is not None:
        _ensure_non_negative_fee_amount(normalized_amount, field_name=field_name)
    return normalized_amount


def _has_fee_components(fee_components: Mapping[str, object]) -> bool:
    return any(value is not None for value in fee_components.values())


def _total_fee_component_amount(fee_components: Mapping[str, object]) -> Decimal:
    return sum(
        _validated_fee_component_amount(value, field_name=field_name)
        for field_name, value in fee_components.items()
    )


def _validated_fee_component_amount(value: object, *, field_name: str) -> Decimal:
    amount = _fee_component_amount(value, field_name=field_name)
    _ensure_non_negative_fee_amount(amount, field_name=field_name)
    return amount


def _ensure_non_negative_fee_amount(amount: Decimal, *, field_name: str) -> None:
    if amount < 0:
        raise ValueError(f"{field_name} must be greater than or equal to zero.")
