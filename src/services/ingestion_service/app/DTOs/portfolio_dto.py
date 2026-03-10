from datetime import date
from typing import List, Optional

from portfolio_common.cost_basis import CostBasisMethod, normalize_cost_basis_method
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Portfolio(BaseModel):
    portfolio_id: str = Field(
        ...,
        description=(
            "Canonical portfolio identifier used across all downstream "
            "calculators and query surfaces."
        ),
        examples=["DEMO_DPM_EUR_001"],
    )
    base_currency: str = Field(
        ...,
        description="Portfolio base currency used for valuation, P&L, and reporting aggregation.",
        examples=["EUR"],
    )
    open_date: date = Field(
        ...,
        description=(
            "Portfolio activation date from which transactions and positions "
            "are considered valid."
        ),
        examples=["2025-01-01"],
    )
    close_date: Optional[date] = Field(
        None,
        description=(
            "Optional portfolio closure date after which new activity should "
            "not be accepted."
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
            "Booking-center or legal-entity code that owns the portfolio "
            "record operationally."
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
            "Optional adviser or relationship-manager identifier associated "
            "with the portfolio."
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
            "Canonical cost-basis method used for sell linkage and realized "
            "P&L calculation."
        ),
        examples=["FIFO"],
    )

    @field_validator("cost_basis_method", mode="before")
    @classmethod
    def _normalize_cost_basis_method(cls, value: object) -> CostBasisMethod:
        return normalize_cost_basis_method(value)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "portfolio_id": "DEMO_DPM_EUR_001",
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
