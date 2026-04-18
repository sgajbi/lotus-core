from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CashAccountRecord(BaseModel):
    cash_account_id: str = Field(
        ...,
        description="Canonical Lotus cash account identifier.",
        examples=["CASH-ACC-USD-001"],
    )
    portfolio_id: str = Field(
        ...,
        description="Owning portfolio identifier.",
        examples=["PORT-001"],
    )
    security_id: str = Field(
        ...,
        description="Linked cash instrument/security identifier.",
        examples=["CASH_USD"],
    )
    display_name: str = Field(
        ...,
        description="Cash account display name.",
        examples=["USD Operating Cash"],
    )
    account_currency: str = Field(
        ...,
        description="Native cash account currency.",
        examples=["USD"],
    )
    account_role: str | None = Field(
        None,
        description="Optional cash-account role classification.",
        examples=["OPERATING_CASH"],
    )
    lifecycle_status: str = Field(
        ...,
        description="Cash-account lifecycle status.",
        examples=["ACTIVE"],
    )
    opened_on: date | None = Field(
        None,
        description="Cash-account open date when known.",
        examples=["2026-01-01"],
    )
    closed_on: date | None = Field(
        None,
        description="Cash-account close date when known.",
        examples=["2026-12-31"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream source system.",
        examples=["lotus-manage"],
    )

    model_config = ConfigDict(from_attributes=True)


class CashAccountQueryResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-001"])
    resolved_as_of_date: date | None = Field(
        None,
        description="Effective as-of date used to resolve the cash-account master set.",
        examples=["2026-03-28"],
    )
    cash_accounts: list[CashAccountRecord] = Field(
        ...,
        description="Canonical cash accounts linked to the portfolio.",
        examples=[
            [
                {
                    "cash_account_id": "CASH-ACC-USD-001",
                    "portfolio_id": "PORT-001",
                    "security_id": "CASH_USD",
                    "display_name": "USD Operating Cash",
                    "account_currency": "USD",
                    "account_role": "OPERATING_CASH",
                    "lifecycle_status": "ACTIVE",
                    "opened_on": "2026-01-01",
                    "closed_on": None,
                    "source_system": "lotus-manage",
                }
            ]
        ],
    )
