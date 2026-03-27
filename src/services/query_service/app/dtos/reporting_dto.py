from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ReportingScopeType = Literal["portfolio", "portfolio_list", "business_unit"]
AllocationDimension = Literal[
    "asset_class",
    "currency",
    "sector",
    "country",
    "product_type",
    "rating",
    "issuer_id",
    "issuer_name",
    "ultimate_parent_issuer_id",
    "ultimate_parent_issuer_name",
]


class ReportingScope(BaseModel):
    portfolio_id: str | None = Field(
        None,
        description="Single portfolio identifier for portfolio-scoped reporting.",
        examples=["PORT-001"],
    )
    portfolio_ids: list[str] = Field(
        default_factory=list,
        description="Explicit portfolio list for multi-portfolio reporting.",
        examples=[["PORT-001", "PORT-002"]],
    )
    booking_center_code: str | None = Field(
        None,
        description="Business-unit scope using lotus-core booking center ownership.",
        examples=["SGPB"],
    )

    @model_validator(mode="after")
    def validate_exactly_one_scope(self) -> "ReportingScope":
        selected = 0
        if self.portfolio_id:
            selected += 1
        if self.portfolio_ids:
            selected += 1
        if self.booking_center_code:
            selected += 1
        if selected != 1:
            raise ValueError(
                "Exactly one scope selector is required: "
                "portfolio_id, portfolio_ids, or booking_center_code."
            )
        if any(not value.strip() for value in self.portfolio_ids):
            raise ValueError("portfolio_ids cannot contain blank identifiers.")
        return self

    @property
    def scope_type(self) -> ReportingScopeType:
        if self.portfolio_id:
            return "portfolio"
        if self.portfolio_ids:
            return "portfolio_list"
        return "business_unit"


class AssetsUnderManagementQueryRequest(BaseModel):
    scope: ReportingScope = Field(..., description="Portfolio, multi-portfolio, or BU scope.")
    as_of_date: date | None = Field(
        None,
        description="As-of date for the valuation snapshot. Defaults to the latest business date.",
        examples=["2026-03-27"],
    )
    reporting_currency: str | None = Field(
        None,
        description=(
            "Optional reporting currency. Defaults to the portfolio currency for single-portfolio "
            "queries and is required for portfolio-list or BU scopes."
        ),
        examples=["USD"],
    )

    @model_validator(mode="after")
    def validate_reporting_currency_requirements(self) -> "AssetsUnderManagementQueryRequest":
        if self.scope.scope_type != "portfolio" and not self.reporting_currency:
            raise ValueError(
                "reporting_currency is required for portfolio-list and business-unit AUM queries."
            )
        return self


class AssetAllocationQueryRequest(BaseModel):
    scope: ReportingScope = Field(..., description="Portfolio, multi-portfolio, or BU scope.")
    as_of_date: date | None = Field(
        None,
        description="As-of date for the valuation snapshot. Defaults to the latest business date.",
        examples=["2026-03-27"],
    )
    reporting_currency: str | None = Field(
        None,
        description=(
            "Optional reporting currency. Defaults to the portfolio currency for single-portfolio "
            "queries and is required for portfolio-list or BU scopes."
        ),
        examples=["USD"],
    )
    dimensions: list[AllocationDimension] = Field(
        ...,
        min_length=1,
        description=(
            "Classification dimensions to return as allocation views. Supported values reflect "
            "lotus-core instrument classifications."
        ),
        examples=[["asset_class", "currency", "sector"]],
    )

    @model_validator(mode="after")
    def validate_reporting_currency_requirements(self) -> "AssetAllocationQueryRequest":
        if self.scope.scope_type != "portfolio" and not self.reporting_currency:
            raise ValueError(
                "reporting_currency is required for portfolio-list "
                "and business-unit allocation queries."
            )
        return self


class CashBalancesQueryRequest(BaseModel):
    portfolio_id: str = Field(
        ...,
        description="Portfolio identifier for the cash-balance query.",
        examples=["PORT-001"],
    )
    as_of_date: date | None = Field(
        None,
        description="As-of date for the valuation snapshot. Defaults to the latest business date.",
        examples=["2026-03-27"],
    )
    reporting_currency: str | None = Field(
        None,
        description=(
            "Optional reporting currency. Defaults to the portfolio currency when not provided."
        ),
        examples=["USD"],
    )


class ReportingPortfolioSummary(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-001"])
    booking_center_code: str = Field(
        ..., description="Business-unit / booking-center code.", examples=["SGPB"]
    )
    client_id: str = Field(..., description="Client/CIF identifier.", examples=["CIF-1001"])
    portfolio_currency: str = Field(..., description="Portfolio base currency.", examples=["USD"])
    aum_portfolio_currency: Decimal | None = Field(
        None,
        description="Portfolio AUM in portfolio currency. Present for single-portfolio results.",
        examples=["1250000.50"],
    )
    aum_reporting_currency: Decimal = Field(
        ...,
        description="Portfolio AUM in the effective reporting currency.",
        examples=["1250000.50"],
    )
    position_count: int = Field(
        ...,
        description="Number of non-zero positions contributing to AUM.",
    )


class AssetsUnderManagementTotals(BaseModel):
    portfolio_count: int = Field(
        ...,
        description="Number of portfolios included in the result.",
    )
    position_count: int = Field(
        ...,
        description="Number of non-zero positions included in the result.",
    )
    aum_reporting_currency: Decimal = Field(
        ..., description="Aggregated assets under management in reporting currency."
    )


class AssetsUnderManagementResponse(BaseModel):
    scope_type: ReportingScopeType = Field(..., description="Resolved reporting scope type.")
    scope: ReportingScope = Field(..., description="Echoed scope payload.")
    resolved_as_of_date: date = Field(..., description="Effective as-of date used by the query.")
    reporting_currency: str = Field(..., description="Effective reporting currency.")
    totals: AssetsUnderManagementTotals = Field(..., description="Scope-level AUM totals.")
    portfolios: list[ReportingPortfolioSummary] = Field(
        ..., description="Per-portfolio AUM breakdown for the resolved scope."
    )


class AllocationBucket(BaseModel):
    dimension_value: str = Field(
        ..., description="Resolved classification label for the allocation bucket."
    )
    market_value_reporting_currency: Decimal = Field(
        ..., description="Bucket market value in the effective reporting currency."
    )
    weight: Decimal = Field(
        ..., description="Bucket market-value weight versus the total AUM of the scope."
    )
    position_count: int = Field(..., description="Number of positions contributing to the bucket.")


class AllocationView(BaseModel):
    dimension: AllocationDimension = Field(..., description="Classification dimension.")
    total_market_value_reporting_currency: Decimal = Field(
        ..., description="Total market value represented by this view."
    )
    buckets: list[AllocationBucket] = Field(
        ..., description="Allocation buckets for the requested dimension."
    )


class AssetAllocationResponse(BaseModel):
    scope_type: ReportingScopeType = Field(..., description="Resolved reporting scope type.")
    scope: ReportingScope = Field(..., description="Echoed scope payload.")
    resolved_as_of_date: date = Field(..., description="Effective as-of date used by the query.")
    reporting_currency: str = Field(..., description="Effective reporting currency.")
    total_market_value_reporting_currency: Decimal = Field(
        ..., description="Total AUM represented by the allocation views."
    )
    views: list[AllocationView] = Field(
        ..., description="Allocation views for the requested classification dimensions."
    )


class CashAccountBalanceRecord(BaseModel):
    cash_account_id: str = Field(
        ...,
        description=(
            "Lotus cash account identifier. Resolved from the latest known settlement cash account "
            "mapping when available, otherwise from the cash instrument identity."
        ),
        examples=["CASH-ACC-USD-001"],
    )
    instrument_id: str = Field(
        ...,
        description="Cash instrument identifier.",
        examples=["CASH_USD"],
    )
    security_id: str = Field(
        ...,
        description="Cash security identifier.",
        examples=["CASH_USD"],
    )
    account_currency: str = Field(
        ...,
        description="Native cash account currency.",
        examples=["USD"],
    )
    instrument_name: str = Field(..., description="Display name for the cash account.")
    balance_account_currency: Decimal = Field(
        ..., description="Cash balance in native cash account currency."
    )
    balance_portfolio_currency: Decimal = Field(
        ..., description="Cash balance translated to portfolio currency."
    )
    balance_reporting_currency: Decimal = Field(
        ..., description="Cash balance translated to the effective reporting currency."
    )


class CashBalancesTotals(BaseModel):
    cash_account_count: int = Field(..., description="Number of cash accounts returned.")
    total_balance_portfolio_currency: Decimal = Field(
        ..., description="Total cash balance in portfolio currency."
    )
    total_balance_reporting_currency: Decimal = Field(
        ..., description="Total cash balance in reporting currency."
    )


class CashBalancesResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.")
    portfolio_currency: str = Field(..., description="Portfolio base currency.")
    reporting_currency: str = Field(..., description="Effective reporting currency.")
    resolved_as_of_date: date = Field(..., description="Effective as-of date used by the query.")
    totals: CashBalancesTotals = Field(..., description="Portfolio-level cash totals.")
    cash_accounts: list[CashAccountBalanceRecord] = Field(
        ..., description="Resolved cash accounts and balances for the portfolio."
    )
