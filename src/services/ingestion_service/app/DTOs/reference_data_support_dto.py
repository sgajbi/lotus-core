from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClassificationTaxonomyRecord(BaseModel):
    classification_set_id: str = Field(
        ..., description="Classification set identifier.", examples=["wm_global_taxonomy_v1"]
    )
    taxonomy_scope: str = Field(..., description="Taxonomy scope.", examples=["index"])
    dimension_name: str = Field(..., description="Dimension name.", examples=["sector"])
    dimension_value: str = Field(..., description="Dimension value.", examples=["technology"])
    dimension_description: str | None = Field(
        None,
        description="Dimension description.",
        examples=["Technology sector classification"],
    )
    effective_from: date = Field(..., description="Effective start date.", examples=["2025-01-01"])
    effective_to: date | None = Field(
        None, description="Effective end date.", examples=["2026-12-31"]
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the taxonomy record.",
        examples=["2026-01-31T23:00:00Z"],
    )
    source_vendor: str | None = Field(
        None, description="Source vendor.", examples=["LOTUS_TAXONOMY"]
    )
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["tax_20260131"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class CashAccountMasterRecord(BaseModel):
    cash_account_id: str = Field(
        ..., description="Canonical Lotus cash account identifier.", examples=["CASH-ACC-USD-001"]
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
        ..., description="Cash account display name.", examples=["USD Operating Cash"]
    )
    account_currency: str = Field(
        ...,
        description=(
            "Canonical three-letter native cash account currency used for cash balance, "
            "settlement, liquidity, and FX readiness calculations."
        ),
        examples=["USD"],
    )
    account_role: str | None = Field(
        None,
        description="Optional account role label.",
        examples=["OPERATING_CASH"],
    )
    lifecycle_status: str = Field(
        "ACTIVE",
        description="Cash account lifecycle status.",
        examples=["ACTIVE"],
    )
    opened_on: date | None = Field(
        None,
        description="Optional cash account open date.",
        examples=["2026-01-01"],
    )
    closed_on: date | None = Field(
        None,
        description="Optional cash account close date.",
        examples=["2026-12-31"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream source system.",
        examples=["lotus-manage"],
    )
    source_record_id: str | None = Field(
        None,
        description="Upstream source record identifier.",
        examples=["cash-account-001"],
    )

    @field_validator("account_currency", mode="before")
    @classmethod
    def _normalize_account_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    model_config = ConfigDict()


class InstrumentLookthroughComponentRecord(BaseModel):
    parent_security_id: str = Field(
        ...,
        description="Structured product or fund security identifier being decomposed.",
        examples=["FUND_GLOBAL_60_40"],
    )
    component_security_id: str = Field(
        ...,
        description="Underlying component security identifier.",
        examples=["ETF_WORLD_EQUITY"],
    )
    effective_from: date = Field(
        ...,
        description="Effective start date for the look-through composition row.",
        examples=["2026-01-01"],
    )
    effective_to: date | None = Field(
        None,
        description="Effective end date for the look-through composition row.",
        examples=["2026-12-31"],
    )
    component_weight: Decimal = Field(
        ...,
        ge=Decimal(0),
        le=Decimal(1),
        description="Weight of the underlying component between 0 and 1.",
        examples=["0.6000000000"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream source system.",
        examples=["lotus-manage"],
    )
    source_record_id: str | None = Field(
        None,
        description="Upstream source record identifier.",
        examples=["lt-001"],
    )

    model_config = ConfigDict()


class ClassificationTaxonomyIngestionRequest(BaseModel):
    classification_taxonomy: list[ClassificationTaxonomyRecord] = Field(
        ...,
        description="Classification taxonomy records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "classification_set_id": "wm_global_taxonomy_v1",
                    "taxonomy_scope": "index",
                    "dimension_name": "sector",
                    "dimension_value": "technology",
                    "effective_from": "2025-01-01",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class CashAccountMasterIngestionRequest(BaseModel):
    cash_accounts: list[CashAccountMasterRecord] = Field(
        ...,
        description="Cash-account master records to ingest or upsert.",
        min_length=1,
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
                }
            ]
        ],
    )

    model_config = ConfigDict()


class InstrumentLookthroughComponentIngestionRequest(BaseModel):
    lookthrough_components: list[InstrumentLookthroughComponentRecord] = Field(
        ...,
        description="Instrument look-through composition rows to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "parent_security_id": "FUND_GLOBAL_60_40",
                    "component_security_id": "ETF_WORLD_EQUITY",
                    "effective_from": "2026-01-01",
                    "component_weight": "0.6000000000",
                }
            ]
        ],
    )

    model_config = ConfigDict()
