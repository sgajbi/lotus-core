from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .reference_integration_dto import IntegrationWindow
from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)

SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES = (
    "cashflow",
    "fee",
    "income",
    "tax",
    "realized_capital_pnl",
    "realized_fx_pnl",
    "realized_total_pnl",
    "fx_context",
)


def _normalize_optional_identifiers(values: list[str] | None, field_name: str) -> list[str] | None:
    if values is None:
        return None
    normalized = [value.strip() for value in values]
    if any(not value for value in normalized):
        raise ValueError(f"{field_name} must not contain blank values")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _normalize_transaction_types(transaction_types: list[str] | None) -> list[str] | None:
    normalized = _normalize_optional_identifiers(transaction_types, "transaction_types")
    if normalized is None:
        return None
    return [transaction_type.upper() for transaction_type in normalized]


class PerformanceComponentEconomicsRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business as-of date used to bound source-authored economics evidence.",
        examples=["2026-05-10"],
    )
    window: IntegrationWindow = Field(
        ...,
        description="Inclusive transaction-date window used to source economics evidence.",
    )
    security_ids: list[str] | None = Field(
        None,
        description="Optional security identifiers used to restrict component economics evidence.",
        examples=[["EQ_US_AAPL", "BOND_US_TSY_10Y"]],
    )
    transaction_types: list[str] | None = Field(
        None,
        description="Optional transaction types used to restrict component economics evidence.",
        examples=[["BUY", "SELL", "DIVIDEND", "INTEREST"]],
    )
    tenant_id: str | None = Field(
        None,
        description=(
            "Tenant scope for future policy enforcement. Null until tenant partitioning is active."
        ),
        examples=["tenant_sg_pb"],
    )

    @model_validator(mode="after")
    def validate_scope(self) -> "PerformanceComponentEconomicsRequest":
        if self.window.end_date < self.window.start_date:
            raise ValueError("window.end_date must be on or after window.start_date")
        self.security_ids = _normalize_optional_identifiers(self.security_ids, "security_ids")
        self.transaction_types = _normalize_transaction_types(self.transaction_types)
        return self

    model_config = ConfigDict()


class PerformanceComponentEconomicsRow(BaseModel):
    transaction_id: str = Field(
        ..., description="Source transaction identifier.", examples=["TXN-DIV-001"]
    )
    portfolio_id: str = Field(
        ..., description="Portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    security_id: str = Field(..., description="Security identifier.", examples=["EQ_US_AAPL"])
    transaction_type: str = Field(
        ..., description="Source transaction type.", examples=["DIVIDEND"]
    )
    transaction_date: date = Field(
        ..., description="Transaction date for economics evidence.", examples=["2026-05-10"]
    )
    currency: str = Field(..., description="Transaction economics currency.", examples=["USD"])
    gross_transaction_amount: Decimal = Field(
        ..., description="Gross transaction amount recorded by core.", examples=["125.0000000000"]
    )
    trade_fee_amount: Decimal = Field(
        ...,
        description="Source-authored transaction fee amount from cost rows or trade_fee.",
        examples=["2.5000000000"],
    )
    cashflow_amount: Decimal | None = Field(
        None,
        description="Linked cashflow amount when a cashflow row exists.",
        examples=["100.0000000000"],
    )
    cashflow_currency: str | None = Field(
        None, description="Linked cashflow currency when a cashflow row exists.", examples=["USD"]
    )
    cashflow_classification: str | None = Field(
        None,
        description="Core cashflow classification when a cashflow row exists.",
        examples=["dividend"],
    )
    cashflow_timing: str | None = Field(
        None, description="Core cashflow timing when a cashflow row exists.", examples=["eod"]
    )
    is_position_flow: bool | None = Field(
        None, description="True when the linked cashflow is position-scoped.", examples=[True]
    )
    is_portfolio_flow: bool | None = Field(
        None, description="True when the linked cashflow is portfolio-scoped.", examples=[False]
    )
    withholding_tax_amount: Decimal = Field(
        ...,
        description="Explicit withholding-tax amount recorded on the transaction.",
        examples=["15.0000000000"],
    )
    other_interest_deductions_amount: Decimal = Field(
        ...,
        description="Explicit other interest deductions recorded on the transaction.",
        examples=["5.0000000000"],
    )
    net_interest_amount: Decimal = Field(
        ...,
        description="Explicit net interest or income amount recorded on the transaction.",
        examples=["80.0000000000"],
    )
    realized_capital_pnl_local: Decimal = Field(
        ...,
        description="Realized capital P&L in local currency when recorded.",
        examples=["10.0000000000"],
    )
    realized_fx_pnl_local: Decimal = Field(
        ...,
        description="Realized FX P&L in local currency when recorded.",
        examples=["3.0000000000"],
    )
    realized_total_pnl_local: Decimal = Field(
        ...,
        description="Realized total P&L in local currency when recorded.",
        examples=["13.0000000000"],
    )
    realized_capital_pnl_base: Decimal = Field(
        ...,
        description="Realized capital P&L in portfolio/base currency when recorded.",
        examples=["10.0000000000"],
    )
    realized_fx_pnl_base: Decimal = Field(
        ...,
        description="Realized FX P&L in portfolio/base currency when recorded.",
        examples=["3.0000000000"],
    )
    realized_total_pnl_base: Decimal = Field(
        ...,
        description="Realized total P&L in portfolio/base currency when recorded.",
        examples=["13.0000000000"],
    )
    transaction_fx_rate: Decimal | None = Field(
        None,
        description="Transaction FX rate recorded by core when available.",
        examples=["1.2500000000"],
    )
    fx_contract_id: str | None = Field(
        None, description="Linked FX contract identifier when available.", examples=["FXC-001"]
    )
    source_lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Row-level source lineage for component economics evidence.",
        examples=[
            {
                "source_system": "transactions",
                "contract_version": "performance_component_economics_v1",
            }
        ],
    )

    model_config = ConfigDict()


class PerformanceComponentEconomicsTotal(BaseModel):
    component_family: str = Field(
        ...,
        description="Component economics family represented by this total.",
        examples=["income"],
    )
    currency: str = Field(..., description="Currency for this total.", examples=["USD"])
    amount: Decimal = Field(
        ..., description="Source-authored component amount.", examples=["80.0000000000"]
    )
    evidence_count: int = Field(
        ...,
        ge=0,
        description="Number of rows contributing to this component total.",
        examples=[1],
    )

    model_config = ConfigDict()


class PerformanceComponentEconomicsSupportability(BaseModel):
    state: Literal["READY", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for source-authored performance component economics.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Machine-readable supportability reason.",
        examples=["PERFORMANCE_COMPONENT_ECONOMICS_READY"],
    )
    source_owner: Literal["lotus-core"] = Field(
        "lotus-core", description="Repository that owns this source economics contract."
    )
    downstream_consumer: Literal["lotus-performance"] = Field(
        "lotus-performance",
        description="Primary downstream consumer for contribution analytics.",
    )
    source_row_count: int = Field(
        ...,
        ge=0,
        description="Number of source transaction rows returned.",
        examples=[8],
    )
    supported_component_families: list[str] = Field(
        default_factory=lambda: list(SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES),
        description="Component families this contract can source-author from core data.",
    )
    observed_component_families: list[str] = Field(
        default_factory=list,
        description="Component families observed in the returned source rows.",
    )
    missing_component_families: list[str] = Field(
        default_factory=list,
        description=(
            "Supported component families with no evidence in this response. Missing does not "
            "mean fabricated zero; downstream must decide whether the requested workflow needs "
            "that family."
        ),
    )

    model_config = ConfigDict()


class PerformanceComponentEconomicsResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PerformanceComponentEconomics"] = product_name_field(
        "PerformanceComponentEconomics"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ..., description="Portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    as_of_date: date = Field(
        ..., description="Business as-of date used for the response.", examples=["2026-05-10"]
    )
    window: IntegrationWindow = Field(..., description="Resolved evidence window.")
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for this component-economics scope.",
        examples=["1f7f4cf0f79e4a0ba4e555c4db9c0f34"],
    )
    rows: list[PerformanceComponentEconomicsRow] = Field(
        default_factory=list,
        description="Deterministically ordered source-authored component economics rows.",
    )
    component_totals: list[PerformanceComponentEconomicsTotal] = Field(
        default_factory=list,
        description="Grouped source-authored component economics totals.",
    )
    supportability: PerformanceComponentEconomicsSupportability = Field(
        ..., description="Supportability and coverage posture for the response."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Product-level source lineage for component economics evidence.",
        examples=[
            {
                "source_system": "transactions",
                "source_table": "transactions,cashflows,transaction_costs",
                "contract_version": "performance_component_economics_v1",
            }
        ],
    )

    model_config = ConfigDict()
