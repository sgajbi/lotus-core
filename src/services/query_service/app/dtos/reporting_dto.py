from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)

ReportingScopeType = Literal["portfolio", "portfolio_list", "business_unit"]
IncomeType = Literal["DIVIDEND", "INTEREST", "CASH_IN_LIEU"]
ActivityBucketType = Literal["INFLOWS", "OUTFLOWS", "FEES", "TAXES"]
LookThroughMode = Literal["direct_only", "prefer_look_through"]
AllocationDimension = Literal[
    "asset_class",
    "currency",
    "sector",
    "country",
    "region",
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


class ReportingWindow(BaseModel):
    start_date: date = Field(
        ...,
        description="Inclusive start date for the requested reporting window.",
        examples=["2026-01-01"],
    )
    end_date: date = Field(
        ...,
        description="Inclusive end date for the requested reporting window.",
        examples=["2026-03-27"],
    )

    @model_validator(mode="after")
    def validate_date_order(self) -> "ReportingWindow":
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date.")
        return self


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
    look_through_mode: LookThroughMode = Field(
        "direct_only",
        description=(
            "Allocation decomposition mode. `direct_only` keeps parent holdings intact. "
            "`prefer_look_through` decomposes eligible parent instruments when source-owned "
            "look-through components are available."
        ),
        examples=["prefer_look_through"],
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


class PortfolioSummaryQueryRequest(BaseModel):
    portfolio_id: str = Field(
        ...,
        description="Portfolio identifier for the summary query.",
        examples=["PORT-001"],
    )
    as_of_date: date | None = Field(
        None,
        description=(
            "As-of date for the historical portfolio snapshot. Defaults to latest business date."
        ),
        examples=["2026-03-27"],
    )
    reporting_currency: str | None = Field(
        None,
        description="Optional reporting currency. Defaults to the portfolio currency.",
        examples=["USD"],
    )


class HoldingsSnapshotQueryRequest(BaseModel):
    portfolio_id: str = Field(
        ...,
        description="Portfolio identifier for the holdings snapshot query.",
        examples=["PORT-001"],
    )
    as_of_date: date | None = Field(
        None,
        description=(
            "As-of date for the historical holdings snapshot. Defaults to latest business date."
        ),
        examples=["2026-03-27"],
    )
    reporting_currency: str | None = Field(
        None,
        description="Optional reporting currency. Defaults to the portfolio currency.",
        examples=["USD"],
    )
    include_cash_positions: bool = Field(
        True,
        description="When false, excludes cash positions from the holdings snapshot.",
        examples=[True],
    )


class IncomeSummaryQueryRequest(BaseModel):
    scope: ReportingScope = Field(..., description="Portfolio, multi-portfolio, or BU scope.")
    window: ReportingWindow = Field(
        ...,
        description=(
            "Requested reporting window. The response also includes year-to-date values "
            "anchored to window.end_date."
        ),
    )
    reporting_currency: str | None = Field(
        None,
        description=(
            "Optional reporting currency. Defaults to the portfolio currency for single-portfolio "
            "queries and is required for portfolio-list or BU scopes."
        ),
        examples=["USD"],
    )
    income_types: list[IncomeType] = Field(
        default_factory=lambda: ["DIVIDEND", "INTEREST", "CASH_IN_LIEU"],
        description=(
            "Income transaction types to include. Defaults to the full canonical Lotus income set."
        ),
        examples=[["DIVIDEND", "INTEREST"]],
    )

    @model_validator(mode="after")
    def validate_reporting_currency_requirements(self) -> "IncomeSummaryQueryRequest":
        if self.scope.scope_type != "portfolio" and not self.reporting_currency:
            raise ValueError(
                "reporting_currency is required for portfolio-list and "
                "business-unit income queries."
            )
        return self


class ActivitySummaryQueryRequest(BaseModel):
    scope: ReportingScope = Field(..., description="Portfolio, multi-portfolio, or BU scope.")
    window: ReportingWindow = Field(
        ...,
        description=(
            "Requested reporting window. The response also includes year-to-date values "
            "anchored to window.end_date."
        ),
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
    def validate_reporting_currency_requirements(self) -> "ActivitySummaryQueryRequest":
        if self.scope.scope_type != "portfolio" and not self.reporting_currency:
            raise ValueError(
                "reporting_currency is required for portfolio-list "
                "and business-unit activity queries."
            )
        return self


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
        ...,
        description="Resolved classification label for the allocation bucket.",
        examples=["Equity"],
    )
    market_value_reporting_currency: Decimal = Field(
        ...,
        description="Bucket market value in the effective reporting currency.",
        examples=[600000.0],
    )
    weight: Decimal = Field(
        ...,
        description="Bucket market-value weight versus the total AUM of the scope.",
        examples=[0.6],
    )
    position_count: int = Field(
        ...,
        description="Number of positions contributing to the bucket.",
        examples=[3],
    )


class AllocationView(BaseModel):
    dimension: AllocationDimension = Field(
        ...,
        description="Classification dimension.",
        examples=["asset_class"],
    )
    total_market_value_reporting_currency: Decimal = Field(
        ...,
        description="Total market value represented by this view.",
        examples=[1000000.0],
    )
    buckets: list[AllocationBucket] = Field(
        ..., description="Allocation buckets for the requested dimension."
    )


class AssetAllocationResponse(BaseModel):
    scope_type: ReportingScopeType = Field(..., description="Resolved reporting scope type.")
    scope: ReportingScope = Field(..., description="Echoed scope payload.")
    resolved_as_of_date: date = Field(
        ...,
        description="Effective as-of date used by the query.",
        examples=["2026-03-27"],
    )
    reporting_currency: str = Field(
        ...,
        description="Effective reporting currency.",
        examples=["USD"],
    )
    total_market_value_reporting_currency: Decimal = Field(
        ...,
        description="Total AUM represented by the allocation views.",
        examples=[1000000.0],
    )
    look_through: "AllocationLookThroughInfo" = Field(
        ...,
        description="Applied look-through mode and capability summary for the allocation query.",
    )
    views: list[AllocationView] = Field(
        ..., description="Allocation views for the requested classification dimensions."
    )


class AllocationLookThroughInfo(BaseModel):
    requested_mode: LookThroughMode = Field(
        ...,
        description="Look-through mode requested by the caller.",
        examples=["prefer_look_through"],
    )
    applied_mode: LookThroughMode = Field(
        ...,
        description="Look-through mode actually applied to the response.",
        examples=["direct_only"],
    )
    supported: bool = Field(
        ...,
        description="Whether source-owned look-through decomposition was available for the query.",
        examples=[True],
    )
    decomposed_position_count: int = Field(
        ...,
        description="Number of parent positions decomposed into underlying components.",
        examples=[2],
    )
    limitation_reason: str | None = Field(
        None,
        description="Explanation when look-through was requested but could not be applied.",
        examples=["Look-through was unavailable for one or more parent fund positions."],
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


class CashBalancesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["HoldingsAsOf"] = product_name_field("HoldingsAsOf")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier.")
    portfolio_currency: str = Field(..., description="Portfolio base currency.")
    reporting_currency: str = Field(..., description="Effective reporting currency.")
    resolved_as_of_date: date = Field(..., description="Effective as-of date used by the query.")
    totals: CashBalancesTotals = Field(..., description="Portfolio-level cash totals.")
    cash_accounts: list[CashAccountBalanceRecord] = Field(
        ..., description="Resolved cash accounts and balances for the portfolio."
    )


class PortfolioSummaryTotals(BaseModel):
    total_market_value_portfolio_currency: Decimal = Field(
        ...,
        description="Total portfolio market value in portfolio currency.",
        examples=[1000000.0],
    )
    total_market_value_reporting_currency: Decimal = Field(
        ...,
        description="Total portfolio market value in reporting currency.",
        examples=[1000000.0],
    )
    cash_balance_portfolio_currency: Decimal = Field(
        ...,
        description="Cash balance subtotal in portfolio currency.",
        examples=[120000.0],
    )
    cash_balance_reporting_currency: Decimal = Field(
        ...,
        description="Cash balance subtotal in reporting currency.",
        examples=[120000.0],
    )
    invested_market_value_portfolio_currency: Decimal = Field(
        ...,
        description="Non-cash invested market value in portfolio currency.",
        examples=[880000.0],
    )
    invested_market_value_reporting_currency: Decimal = Field(
        ...,
        description="Non-cash invested market value in reporting currency.",
        examples=[880000.0],
    )


class PortfolioSummarySnapshotMetadata(BaseModel):
    snapshot_date: date = Field(
        ...,
        description="Resolved snapshot date backing the summary.",
        examples=["2026-03-27"],
    )
    position_count: int = Field(
        ...,
        description="Number of positions in the snapshot.",
        examples=[12],
    )
    cash_account_count: int = Field(
        ...,
        description="Number of cash accounts represented.",
        examples=[2],
    )
    valued_position_count: int = Field(
        ...,
        description="Number of snapshot positions with non-UNVALUED coverage.",
        examples=[11],
    )
    unvalued_position_count: int = Field(
        ...,
        description="Number of snapshot positions still lacking valuation coverage.",
        examples=[1],
    )


class PortfolioSummaryResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-001"])
    booking_center_code: str = Field(..., description="Booking center code.", examples=["SGPB"])
    client_id: str = Field(..., description="Client identifier.", examples=["CIF-1001"])
    portfolio_currency: str = Field(..., description="Portfolio base currency.", examples=["USD"])
    reporting_currency: str = Field(
        ...,
        description="Effective reporting currency.",
        examples=["USD"],
    )
    resolved_as_of_date: date = Field(
        ...,
        description="Effective as-of date used by the query.",
        examples=["2026-03-27"],
    )
    portfolio_type: str = Field(
        ...,
        description="Portfolio product/type classification.",
        examples=["DISCRETIONARY"],
    )
    objective: str | None = Field(
        None,
        description="Primary portfolio objective.",
        examples=["Growth"],
    )
    risk_exposure: str = Field(
        ...,
        description="Risk-exposure classification.",
        examples=["BALANCED"],
    )
    status: str = Field(
        ...,
        description="Portfolio lifecycle status.",
        examples=["ACTIVE"],
    )
    totals: PortfolioSummaryTotals = Field(..., description="Portfolio summary totals.")
    snapshot_metadata: PortfolioSummarySnapshotMetadata = Field(
        ...,
        description="Resolved snapshot metadata for the summary query.",
    )


class HoldingSnapshotRecord(BaseModel):
    security_id: str = Field(..., description="Security identifier.", examples=["SEC-US-AAPL"])
    instrument_name: str = Field(..., description="Instrument display name.")
    asset_class: str | None = Field(None, description="Asset class classification.")
    sector: str | None = Field(None, description="Sector classification.")
    country: str | None = Field(None, description="Country of risk classification.")
    region: str | None = Field(None, description="Derived region classification.")
    account_currency: str | None = Field(None, description="Instrument or account currency.")
    quantity: Decimal = Field(..., description="Position quantity.")
    market_value_portfolio_currency: Decimal = Field(
        ...,
        description="Position market value in portfolio currency.",
    )
    market_value_reporting_currency: Decimal = Field(
        ...,
        description="Position market value in reporting currency.",
    )
    weight: Decimal = Field(..., description="Position weight versus total snapshot market value.")
    valuation_status: str | None = Field(None, description="Snapshot valuation status.")


class HoldingsSnapshotResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["HoldingsAsOf"] = product_name_field("HoldingsAsOf")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-001"])
    portfolio_currency: str = Field(..., description="Portfolio base currency.", examples=["USD"])
    reporting_currency: str = Field(
        ...,
        description="Effective reporting currency.",
        examples=["USD"],
    )
    resolved_as_of_date: date = Field(..., description="Effective as-of date used by the query.")
    snapshot_date: date = Field(
        ...,
        description="Resolved snapshot date backing the holdings view.",
    )
    total_market_value_portfolio_currency: Decimal = Field(
        ...,
        description="Total snapshot market value in portfolio currency.",
    )
    total_market_value_reporting_currency: Decimal = Field(
        ...,
        description="Total snapshot market value in reporting currency.",
    )
    positions: list[HoldingSnapshotRecord] = Field(
        ...,
        description="Holdings snapshot rows for the resolved portfolio and as-of date.",
    )


class IncomePeriodSummary(BaseModel):
    transaction_count: int = Field(..., description="Number of income transactions included.")
    gross_amount_portfolio_currency: Decimal | None = Field(
        None,
        description=(
            "Gross income translated to portfolio currency. Present for single-portfolio totals "
            "and per-portfolio rows."
        ),
    )
    gross_amount_reporting_currency: Decimal = Field(
        ..., description="Gross income translated to the effective reporting currency."
    )
    withholding_tax_portfolio_currency: Decimal | None = Field(
        None,
        description="Withholding tax translated to portfolio currency when applicable.",
    )
    withholding_tax_reporting_currency: Decimal = Field(
        ..., description="Withholding tax translated to reporting currency."
    )
    other_deductions_portfolio_currency: Decimal | None = Field(
        None,
        description="Other income deductions translated to portfolio currency when applicable.",
    )
    other_deductions_reporting_currency: Decimal = Field(
        ..., description="Other income deductions translated to reporting currency."
    )
    net_amount_portfolio_currency: Decimal | None = Field(
        None,
        description="Net income translated to portfolio currency when applicable.",
    )
    net_amount_reporting_currency: Decimal = Field(
        ..., description="Net income translated to the effective reporting currency."
    )


class IncomeTypeSummary(BaseModel):
    income_type: IncomeType = Field(..., description="Canonical Lotus income transaction type.")
    requested_window: IncomePeriodSummary = Field(
        ..., description="Income totals for the requested reporting window."
    )
    year_to_date: IncomePeriodSummary = Field(
        ..., description="Income totals from January 1 through the window end date."
    )


class PortfolioIncomeSummary(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.")
    booking_center_code: str = Field(
        ..., description="Business-unit / booking-center code.", examples=["SGPB"]
    )
    client_id: str = Field(..., description="Client/CIF identifier.", examples=["CIF-1001"])
    portfolio_currency: str = Field(..., description="Portfolio base currency.", examples=["USD"])
    requested_window: IncomePeriodSummary = Field(
        ..., description="Portfolio income totals for the requested reporting window."
    )
    year_to_date: IncomePeriodSummary = Field(
        ..., description="Portfolio income totals from January 1 through the window end date."
    )
    income_types: list[IncomeTypeSummary] = Field(
        ..., description="Breakdown by income transaction type for the portfolio."
    )


class IncomeSummaryTotals(BaseModel):
    portfolio_count: int = Field(..., description="Number of portfolios included in the result.")
    requested_window: IncomePeriodSummary = Field(
        ..., description="Scope-level income totals for the requested reporting window."
    )
    year_to_date: IncomePeriodSummary = Field(
        ..., description="Scope-level income totals from January 1 through the window end date."
    )


class IncomeSummaryResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["TransactionLedgerWindow"] = product_name_field("TransactionLedgerWindow")
    product_version: Literal["v1"] = product_version_field()
    scope_type: ReportingScopeType = Field(..., description="Resolved reporting scope type.")
    scope: ReportingScope = Field(..., description="Echoed scope payload.")
    resolved_window: ReportingWindow = Field(..., description="Effective reporting window used.")
    reporting_currency: str = Field(..., description="Effective reporting currency.")
    totals: IncomeSummaryTotals = Field(..., description="Scope-level income totals.")
    portfolios: list[PortfolioIncomeSummary] = Field(
        ..., description="Per-portfolio income summary rows for the resolved scope."
    )


class FlowPeriodSummary(BaseModel):
    transaction_count: int = Field(..., description="Number of flow records contributing.")
    amount_portfolio_currency: Decimal | None = Field(
        None,
        description=(
            "Flow amount translated to portfolio currency. Present for single-portfolio totals "
            "and per-portfolio rows."
        ),
    )
    amount_reporting_currency: Decimal = Field(
        ..., description="Flow amount translated to the effective reporting currency."
    )


class ActivityBucketSummary(BaseModel):
    bucket: ActivityBucketType = Field(..., description="Canonical portfolio-flow bucket.")
    requested_window: FlowPeriodSummary = Field(
        ..., description="Bucket totals for the requested reporting window."
    )
    year_to_date: FlowPeriodSummary = Field(
        ..., description="Bucket totals from January 1 through the window end date."
    )


class PortfolioActivitySummary(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.")
    booking_center_code: str = Field(
        ..., description="Business-unit / booking-center code.", examples=["SGPB"]
    )
    client_id: str = Field(..., description="Client/CIF identifier.", examples=["CIF-1001"])
    portfolio_currency: str = Field(..., description="Portfolio base currency.", examples=["USD"])
    buckets: list[ActivityBucketSummary] = Field(
        ..., description="Portfolio-level flow buckets for requested-window and YTD views."
    )


class ActivitySummaryTotals(BaseModel):
    portfolio_count: int = Field(..., description="Number of portfolios included in the result.")
    buckets: list[ActivityBucketSummary] = Field(
        ..., description="Scope-level flow buckets for requested-window and YTD views."
    )


class ActivitySummaryResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["TransactionLedgerWindow"] = product_name_field("TransactionLedgerWindow")
    product_version: Literal["v1"] = product_version_field()
    scope_type: ReportingScopeType = Field(..., description="Resolved reporting scope type.")
    scope: ReportingScope = Field(..., description="Echoed scope payload.")
    resolved_window: ReportingWindow = Field(..., description="Effective reporting window used.")
    reporting_currency: str = Field(..., description="Effective reporting currency.")
    totals: ActivitySummaryTotals = Field(..., description="Scope-level activity totals.")
    portfolios: list[PortfolioActivitySummary] = Field(
        ..., description="Per-portfolio activity summary rows for the resolved scope."
    )


AssetAllocationResponse.model_rebuild()
