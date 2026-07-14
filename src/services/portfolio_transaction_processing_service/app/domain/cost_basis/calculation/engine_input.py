"""Map canonical booked transactions to cost-basis engine inputs."""

from dataclasses import fields
from decimal import Decimal
from typing import Any, cast

from portfolio_common.domain.decimal_amount import decimal_or_none
from portfolio_common.domain.transaction.fee_components import resolve_transaction_trade_fee

from ...transaction import BookedTransaction

FEE_COMPONENT_FIELDS = ("brokerage", "stamp_duty", "exchange_fee", "gst", "other_fees")
BOOKED_TRANSACTION_FIELDS = tuple(field.name for field in fields(BookedTransaction))


def normalize_cost_fee_amount(value: object, *, field_name: str) -> Decimal:
    """Normalize a fee value once and reject invalid or negative amounts."""

    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal(0)
    amount = cast(Decimal | None, decimal_or_none(value))
    if amount is None:
        raise ValueError(f"{field_name} must be numeric.")
    return amount


def _fee_components(engine_input: dict[str, Any]) -> dict[str, object]:
    return {field_name: engine_input.pop(field_name, None) for field_name in FEE_COMPONENT_FIELDS}


def build_cost_basis_engine_input(transaction: BookedTransaction) -> dict[str, Any]:
    """Build the typed business payload consumed by cost-basis calculation policies."""

    engine_input = {
        field_name: getattr(transaction, field_name) for field_name in BOOKED_TRANSACTION_FIELDS
    }
    trade_fee = normalize_cost_fee_amount(
        engine_input.pop("trade_fee", Decimal(0)),
        field_name="trade_fee",
    )
    raw_fee_components = _fee_components(engine_input)
    has_fee_components = any(value is not None for value in raw_fee_components.values())
    normalized_components = {
        field_name: normalize_cost_fee_amount(value, field_name=field_name)
        for field_name, value in raw_fee_components.items()
    }
    resolved_trade_fee = resolve_transaction_trade_fee(
        trade_fee,
        normalized_components if has_fee_components else {},
    )

    if has_fee_components:
        engine_input["fees"] = {
            field_name: str(amount) for field_name, amount in normalized_components.items()
        }
        engine_input["trade_fee"] = str(resolved_trade_fee)
    elif resolved_trade_fee > 0:
        engine_input["fees"] = {"brokerage": str(resolved_trade_fee)}
        engine_input["trade_fee"] = str(resolved_trade_fee)
    else:
        engine_input["trade_fee"] = "0"

    return engine_input
