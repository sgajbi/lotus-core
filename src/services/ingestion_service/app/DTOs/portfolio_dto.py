from datetime import date
from typing import List, Optional

from portfolio_common.domain.cost_basis_method import CostBasisMethod, normalize_cost_basis_method
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.valuation import resolve_optional_valuation_book_scope
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Portfolio(BaseModel):
    portfolio_id: str = Field(
        ...,
        description=(
            "Canonical portfolio identifier used across all downstream "
            "calculators and query surfaces."
        ),
        examples=["DEMO_DPM_EUR_001"],
    )
    tenant_id: Optional[str] = Field(
        None,
        description=(
            "Tenant or book-of-record scope for this source-data product. "
            "Null until runtime tenant enforcement is available for this product."
        ),
        examples=["tenant-sg"],
    )
    legal_book_id: Optional[str] = Field(
        None,
        description=(
            "Legal booking entity or governed accounting book. This field must not be "
            "inferred from booking centre or jurisdiction."
        ),
        examples=["LEGAL_BOOK_001"],
    )
    base_currency: str = Field(
        ...,
        description="Portfolio base currency used for valuation, P&L, and reporting aggregation.",
        examples=["EUR"],
    )
    open_date: date = Field(
        ...,
        description=(
            "Portfolio activation date from which transactions and positions are considered valid."
        ),
        examples=["2025-01-01"],
    )
    close_date: Optional[date] = Field(
        None,
        description=(
            "Optional portfolio closure date after which new activity should not be accepted."
        ),
        examples=["2026-12-31"],
    )
    risk_exposure: str = Field(
        ...,
        description=(
            "Client-approved risk exposure classification used for "
            "suitability and analytics segmentation."
        ),
        examples=["balanced"],
    )
    investment_time_horizon: str = Field(
        ...,
        description="Declared investment horizon classification for the portfolio mandate.",
        examples=["long_term"],
    )
    portfolio_type: str = Field(
        ...,
        description="Portfolio operating model or mandate type.",
        examples=["discretionary"],
    )
    objective: Optional[str] = Field(
        None,
        description="Optional textual investment objective used for client and adviser context.",
        examples=["Long-term capital growth with moderated volatility."],
    )
    booking_center_code: str = Field(
        ...,
        description=(
            "Booking-center or legal-entity code that owns the portfolio record operationally."
        ),
        examples=["SG_BOOKING"],
    )
    client_id: str = Field(
        ...,
        description="Canonical client or household identifier that owns the portfolio.",
        examples=["CLIENT_12345"],
    )
    is_leverage_allowed: bool = Field(
        False,
        description="Whether leverage is permitted under the client mandate and policy pack.",
        examples=[False],
    )
    advisor_id: Optional[str] = Field(
        None,
        description=(
            "Optional adviser or relationship-manager identifier associated with the portfolio."
        ),
        examples=["ADV_0042"],
    )
    status: str = Field(
        ...,
        description="Portfolio lifecycle status used by onboarding and query surfaces.",
        examples=["active"],
    )
    cost_basis_method: Optional[CostBasisMethod] = Field(
        CostBasisMethod.FIFO,
        description=(
            "Canonical cost-basis method used for sell linkage and realized P&L calculation."
        ),
        examples=["FIFO"],
    )

    @field_validator("cost_basis_method", mode="before")
    @classmethod
    def _normalize_cost_basis_method(cls, value: object) -> CostBasisMethod:
        return normalize_cost_basis_method(value)

    @field_validator("base_currency", mode="before")
    @classmethod
    def _normalize_base_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    @model_validator(mode="after")
    def _validate_valuation_book_scope(self) -> "Portfolio":
        scope = resolve_optional_valuation_book_scope(
            tenant_id=self.tenant_id,
            legal_book_id=self.legal_book_id,
        )
        if scope is not None:
            self.tenant_id, self.legal_book_id = scope.key
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "portfolio_id": "DEMO_DPM_EUR_001",
                "tenant_id": "tenant-sg",
                "legal_book_id": "LEGAL_BOOK_001",
                "base_currency": "EUR",
                "open_date": "2025-01-01",
                "risk_exposure": "balanced",
                "investment_time_horizon": "long_term",
                "portfolio_type": "discretionary",
                "objective": "Long-term capital growth with moderated volatility.",
                "booking_center_code": "SG_BOOKING",
                "client_id": "CLIENT_12345",
                "is_leverage_allowed": False,
                "advisor_id": "ADV_0042",
                "status": "active",
                "cost_basis_method": "FIFO",
            }
        }
    )


class PortfolioIngestionRequest(BaseModel):
    portfolios: List[Portfolio] = Field(
        ...,
        description="Canonical portfolio master records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "portfolio_id": "DEMO_DPM_EUR_001",
                    "base_currency": "EUR",
                    "open_date": "2025-01-01",
                    "risk_exposure": "balanced",
                    "investment_time_horizon": "long_term",
                    "portfolio_type": "discretionary",
                    "booking_center_code": "SG_BOOKING",
                    "client_id": "CLIENT_12345",
                    "status": "active",
                    "cost_basis_method": "FIFO",
                }
            ]
        ],
    )
