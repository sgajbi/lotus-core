from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from portfolio_common.control_code_normalization import (
    normalize_optional_transaction_control_code,
    normalize_transaction_control_code,
)
from portfolio_common.currency_codes import normalize_currency_code


class InterestCanonicalTransaction(BaseModel):
    """
    Slice 1 canonical INTEREST contract foundation.
    Focuses on deterministic validation and policy/linkage traceability fields.
    """

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    transaction_id: str = Field(..., description="Unique transaction identifier.")
    transaction_type: str = Field(..., description="Canonical transaction type.")

    @field_validator("transaction_type", mode="before")
    @classmethod
    def _normalize_transaction_control_code(cls, value: str | None) -> str:
        return normalize_transaction_control_code(value)

    portfolio_id: str = Field(..., description="Portfolio receiving or paying interest.")
    instrument_id: str = Field(..., description="Instrument identifier.")
    security_id: str = Field(..., description="Security identifier.")

    transaction_date: datetime = Field(..., description="Interest booking timestamp.")
    settlement_date: Optional[datetime] = Field(
        default=None, description="Contractual settlement timestamp."
    )

    quantity: Decimal = Field(..., description="Quantity impact. Canonical INTEREST requires zero.")
    price: Decimal = Field(..., description="Unit price impact. Canonical INTEREST requires zero.")
    gross_transaction_amount: Decimal = Field(
        ..., description="Gross interest amount in trade currency."
    )
    interest_direction: Optional[str] = Field(
        default=None,
        description=(
            "Semantic direction for INTEREST baseline: INCOME or EXPENSE. "
            "When omitted, processing defaults to INCOME."
        ),
    )

    @field_validator("interest_direction", mode="before")
    @classmethod
    def _normalize_optional_transaction_control_code(
        cls, value: str | None
    ) -> str | None:
        return normalize_optional_transaction_control_code(value)

    trade_fee: Optional[Decimal] = Field(
        default=Decimal(0), description="Transaction fee amount if applicable."
    )
    withholding_tax_amount: Optional[Decimal] = Field(
        default=Decimal(0),
        description="Withholding tax amount applied to interest event.",
    )
    other_interest_deductions_amount: Optional[Decimal] = Field(
        default=Decimal(0),
        description="Other non-tax deductions applied to gross interest.",
    )
    net_interest_amount: Optional[Decimal] = Field(
        default=None,
        description=(
            "Optional upstream provided net-interest amount. "
            "When present, must reconcile to gross - withholding - other deductions."
        ),
    )

    trade_currency: str = Field(..., description="Trade/settlement currency.")
    currency: str = Field(..., description="Booked transaction currency.")

    @field_validator("trade_currency", "currency", mode="before")
    @classmethod
    def _normalize_currency_code(cls, value: object) -> str:
        return normalize_currency_code(value)

    economic_event_id: Optional[str] = Field(
        default=None,
        description="Shared economic event identifier used for interest/cash linkage.",
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

    @field_validator("cash_entry_mode", mode="before")
    @classmethod
    def _normalize_optional_cash_entry_mode(cls, value: str | None) -> str | None:
        return normalize_optional_transaction_control_code(value)

    external_cash_transaction_id: Optional[str] = Field(
        default=None,
        description=(
            "Upstream cash transaction identifier when cash_entry_mode is " "UPSTREAM_PROVIDED."
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
        description=("Optional direct cash instrument identifier for generated cash legs."),
    )
