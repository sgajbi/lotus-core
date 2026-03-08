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
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "portfolio_id": "PORT-OPS-001",
                "business_date": "2026-03-06",
                "epoch": 0,
                "requested_by": "ops_control_plane",
                "tolerance": "0.01",
            }
        }
    )
    portfolio_id: str | None = Field(
        default=None,
        description="Optional portfolio scope. When omitted, the run scans all portfolios.",
        examples=["PORT-OPS-001"],
    )
    business_date: date | None = Field(
        default=None,
        description="Optional business date scope.",
        examples=["2026-03-06"],
    )
    epoch: int | None = Field(
        default=None,
        ge=0,
        description="Optional epoch scope.",
        examples=[0],
    )
    requested_by: str | None = Field(
        default=None,
        description="Optional actor label for audit and operational traceability.",
        examples=["ops_control_plane"],
    )
    tolerance: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        description="Optional numeric tolerance override for value comparisons.",
        examples=["0.01"],
    )


class ReconciliationFindingResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "finding_id": "FRF-20260306-0001",
                "run_id": "FRR-20260306-0001",
                "reconciliation_type": "transaction_cashflow",
                "finding_type": "missing_cashflow",
                "severity": "high",
                "portfolio_id": "PORT-OPS-001",
                "security_id": "SEC-US-IBM",
                "transaction_id": "TXN-20260306-0142",
                "business_date": "2026-03-06",
                "epoch": 0,
                "expected_value": {"cashflow_count": 1},
                "observed_value": {"cashflow_count": 0},
                "detail": {
                    "rule_transaction_type": "BUY",
                    "reason": "Transaction has a cashflow rule but no persisted cashflow row."
                },
                "created_at": "2026-03-06T14:03:11Z",
            }
        },
    )
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
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "run_id": "FRR-20260306-0001",
                "reconciliation_type": "transaction_cashflow",
                "portfolio_id": "PORT-OPS-001",
                "business_date": "2026-03-06",
                "epoch": 0,
                "status": "completed",
                "requested_by": "ops_control_plane",
                "correlation_id": "CTL:9b4db9d1-1a39-42f2-9f55-2b2a4f9a4700",
                "tolerance": "0.01",
                "summary": {
                    "checked_transactions": 142,
                    "finding_count": 1,
                    "passed": False,
                },
                "failure_reason": None,
                "started_at": "2026-03-06T14:03:10Z",
                "completed_at": "2026-03-06T14:03:11Z",
                "created_at": "2026-03-06T14:03:10Z",
                "updated_at": "2026-03-06T14:03:11Z",
            }
        },
    )
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
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "runs": [
                    {
                        "run_id": "FRR-20260306-0001",
                        "reconciliation_type": "transaction_cashflow",
                        "portfolio_id": "PORT-OPS-001",
                        "business_date": "2026-03-06",
                        "epoch": 0,
                        "status": "completed",
                        "requested_by": "ops_control_plane",
                        "correlation_id": "CTL:9b4db9d1-1a39-42f2-9f55-2b2a4f9a4700",
                        "tolerance": "0.01",
                        "summary": {
                            "checked_transactions": 142,
                            "finding_count": 1,
                            "passed": False,
                        },
                        "failure_reason": None,
                        "started_at": "2026-03-06T14:03:10Z",
                        "completed_at": "2026-03-06T14:03:11Z",
                        "created_at": "2026-03-06T14:03:10Z",
                        "updated_at": "2026-03-06T14:03:11Z",
                    }
                ],
                "total": 1,
            }
        }
    )
    runs: list[ReconciliationRunResponse]
    total: int


class ReconciliationFindingListResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "findings": [
                    {
                        "finding_id": "FRF-20260306-0001",
                        "run_id": "FRR-20260306-0001",
                        "reconciliation_type": "transaction_cashflow",
                        "finding_type": "missing_cashflow",
                        "severity": "high",
                        "portfolio_id": "PORT-OPS-001",
                        "security_id": "SEC-US-IBM",
                        "transaction_id": "TXN-20260306-0142",
                        "business_date": "2026-03-06",
                        "epoch": 0,
                        "expected_value": {"cashflow_count": 1},
                        "observed_value": {"cashflow_count": 0},
                        "detail": {
                            "rule_transaction_type": "BUY",
                            "reason": (
                                "Transaction has a cashflow rule but no persisted cashflow row."
                            ),
                        },
                        "created_at": "2026-03-06T14:03:11Z",
                    }
                ],
                "total": 1,
            }
        }
    )
    findings: list[ReconciliationFindingResponse]
    total: int
