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
    if not any(value is not None for value in fee_components.values()):
        return trade_fee
    return sum(Decimal(str(value or "0")) for value in fee_components.values())
