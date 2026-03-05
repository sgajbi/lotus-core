from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DividendCanonicalTransaction(BaseModel):
    """
    Slice 1 canonical DIVIDEND contract foundation.
    Focuses on deterministic validation and policy/linkage traceability fields.
    """

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    transaction_id: str = Field(..., description="Unique transaction identifier.")
    transaction_type: str = Field(..., description="Canonical transaction type.")

    portfolio_id: str = Field(..., description="Portfolio receiving distribution.")
    instrument_id: str = Field(..., description="Instrument identifier.")
    security_id: str = Field(..., description="Security identifier.")

    transaction_date: datetime = Field(..., description="Dividend booking timestamp.")
    settlement_date: Optional[datetime] = Field(
        default=None, description="Contractual cash settlement timestamp."
    )

    quantity: Decimal = Field(
        ..., description="Dividend quantity impact. Canonical DIVIDEND requires zero."
    )
    price: Decimal = Field(
        ..., description="Dividend unit price impact. Canonical DIVIDEND requires zero."
    )
    gross_transaction_amount: Decimal = Field(
        ..., description="Gross dividend amount in trade currency."
    )
    trade_fee: Optional[Decimal] = Field(
        default=Decimal(0), description="Transaction fee amount if applicable."
    )

    trade_currency: str = Field(..., description="Trade/settlement currency.")
    currency: str = Field(..., description="Booked transaction currency.")

    economic_event_id: Optional[str] = Field(
        default=None,
        description="Shared economic event identifier used for income/cash linkage.",
    )
    linked_transaction_group_id: Optional[str] = Field(
        default=None, description="Group identifier for linked transactional entries."
    )

    calculation_policy_id: Optional[str] = Field(
        default=None, description="Resolved policy identifier."
    )
    calculation_policy_version: Optional[str] = Field(
        default=None, description="Resolved policy version."
    )
    cash_entry_mode: Optional[str] = Field(
        default=None,
        description=(
            "Cash-leg generation mode. AUTO_GENERATE for service-generated cash leg, "
            "UPSTREAM_PROVIDED for upstream-provided cash entry."
        ),
    )
    external_cash_transaction_id: Optional[str] = Field(
        default=None,
        description=(
            "Upstream cash transaction identifier when cash_entry_mode is "
            "UPSTREAM_PROVIDED."
        ),
    )
    settlement_cash_account_id: Optional[str] = Field(
        default=None,
        description=(
            "Settlement cash account identifier required for AUTO_GENERATE cash-leg "
            "construction."
        ),
    )
    settlement_cash_instrument_id: Optional[str] = Field(
        default=None,
        description=(
            "Optional direct cash instrument identifier for generated cash legs."
        ),
    )
