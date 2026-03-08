from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ReconciliationType = Literal[
    "transaction_cashflow",
    "position_valuation",
    "timeseries_integrity",
]


class ReconciliationRunRequest(BaseModel):
    portfolio_id: str | None = Field(
        default=None,
        description="Optional portfolio scope. When omitted, the run scans all portfolios.",
    )
    business_date: date | None = Field(
        default=None,
        description="Optional business date scope.",
    )
    epoch: int | None = Field(
        default=None,
        ge=0,
        description="Optional epoch scope.",
    )
    requested_by: str | None = Field(
        default=None,
        description="Optional actor label for audit and operational traceability.",
    )
    tolerance: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        description="Optional numeric tolerance override for value comparisons.",
    )


class ReconciliationFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    finding_id: str
    run_id: str
    reconciliation_type: ReconciliationType
    finding_type: str
    severity: str
    portfolio_id: str | None = None
    security_id: str | None = None
    transaction_id: str | None = None
    business_date: date | None = None
    epoch: int | None = None
    expected_value: dict[str, Any] | None = None
    observed_value: dict[str, Any] | None = None
    detail: dict[str, Any] | None = None
    created_at: datetime


class ReconciliationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    run_id: str
    reconciliation_type: ReconciliationType
    portfolio_id: str | None = None
    business_date: date | None = None
    epoch: int | None = None
    status: str
    requested_by: str | None = None
    correlation_id: str | None = None
    tolerance: Decimal | None = None
    summary: dict[str, Any] | None = None
    failure_reason: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReconciliationRunListResponse(BaseModel):
    runs: list[ReconciliationRunResponse]
    total: int


class ReconciliationFindingListResponse(BaseModel):
    findings: list[ReconciliationFindingResponse]
    total: int
