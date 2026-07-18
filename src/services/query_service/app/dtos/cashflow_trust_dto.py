"""Shared response contract for bounded cashflow-window trust evidence."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CashflowWindowTrustResponse(BaseModel):
    """Explain how source cashflow rows reconcile to returned calculation groups."""

    window_status: Literal["POPULATED", "EMPTY", "DEGRADED"] = Field(
        ...,
        description=(
            "Whether the selected source window is populated, explicitly empty, or degraded."
        ),
        examples=["POPULATED"],
    )
    supportability_status: Literal["SUPPORTED", "PARTIAL", "STALE", "UNAVAILABLE"] = Field(
        ...,
        description="Whether this cashflow calculation is supportable from its source evidence.",
        examples=["SUPPORTED"],
    )
    reason_codes: list[str] = Field(
        default_factory=list,
        description=(
            "Bounded reason codes for empty or degraded source evidence. EMPTY_SOURCE_WINDOW is "
            "an explicit supported zero-source result."
        ),
        examples=[["EMPTY_SOURCE_WINDOW"]],
    )
    source_row_count: int = Field(
        ...,
        ge=0,
        description="Source-owned latest cashflow rows selected for the bounded window.",
        examples=[8],
    )
    calculated_source_row_count: int = Field(
        ...,
        ge=0,
        description="Source-row count reconstructed from the calculation inputs.",
        examples=[8],
    )
    output_group_count: int = Field(
        ...,
        ge=0,
        description="Daily points or grouped buckets returned by the product calculation.",
        examples=[31],
    )
    source_component_totals: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Source-query control totals by product-defined component or currency.",
        examples=[{"BOOKED": "2500.00", "PROJECTED": "-15000.00"}],
    )
    calculated_component_totals: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Totals independently accumulated by the returned product calculation.",
        examples=[{"BOOKED": "2500.00", "PROJECTED": "-15000.00"}],
    )
