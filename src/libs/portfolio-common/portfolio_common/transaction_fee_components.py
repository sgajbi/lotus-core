from decimal import Decimal
from typing import Mapping

TRANSACTION_FEE_COMPONENT_FIELDS = (
    "brokerage",
    "stamp_duty",
    "exchange_fee",
    "gst",
    "other_fees",
)


def resolve_transaction_trade_fee(
    trade_fee: Decimal | None,
    fee_components: Mapping[str, object],
) -> Decimal | None:
    if trade_fee is not None:
        normalized_trade_fee = Decimal(str(trade_fee))
        if normalized_trade_fee < 0:
            raise ValueError("trade_fee must be greater than or equal to zero.")
    else:
        normalized_trade_fee = None

    if not any(value is not None for value in fee_components.values()):
        return normalized_trade_fee

    normalized_components: list[Decimal] = []
    for field_name, value in fee_components.items():
        amount = Decimal(str(value or "0"))
        if amount < 0:
            raise ValueError(f"{field_name} must be greater than or equal to zero.")
        normalized_components.append(amount)
    return sum(normalized_components)
