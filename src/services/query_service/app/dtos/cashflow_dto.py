# src/services/query_service/app/dtos/cashflow_dto.py
from pydantic import BaseModel, ConfigDict, Field


class CashflowRecord(BaseModel):
    """
    Represents the cashflow details associated with a transaction
    for API responses.
    """

    amount: float = Field(
        ...,
        description="Signed cashflow amount expressed in the reported cashflow currency.",
        examples=[-18542.0],
    )
    currency: str = Field(
        ...,
        description="ISO 4217 currency code used for the cashflow amount.",
        examples=["USD"],
    )
    classification: str = Field(
        ...,
        description="Canonical cashflow classification used by analytics and reporting.",
        examples=["TRADE_SETTLEMENT"],
    )
    timing: str = Field(
        ...,
        description="Timing bucket used by cashflow analytics, for example SETTLED or PROJECTED.",
        examples=["SETTLED"],
    )
    is_position_flow: bool = Field(
        ...,
        description="True when the cashflow belongs to a specific portfolio-position key.",
        examples=[True],
    )
    is_portfolio_flow: bool = Field(
        ...,
        description=(
            "True when the cashflow is classified at portfolio level rather than position level."
        ),
        examples=[False],
    )
    calculation_type: str = Field(
        ...,
        description="Calculator mode that produced the cashflow row.",
        examples=["TRANSACTION_DERIVED"],
    )

    model_config = ConfigDict(from_attributes=True)

