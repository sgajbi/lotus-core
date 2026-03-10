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
    finding_id: str = Field(
        description="Unique reconciliation finding identifier.",
        examples=["FRF-20260306-0001"],
    )
    run_id: str = Field(
        description="Reconciliation run identifier that owns this finding.",
        examples=["FRR-20260306-0001"],
    )
    reconciliation_type: ReconciliationType = Field(
        description="Control family that produced this finding.",
        examples=["transaction_cashflow"],
    )
    finding_type: str = Field(
        description="Canonical finding classification emitted by the control.",
        examples=["missing_cashflow"],
    )
    severity: str = Field(
        description="Operational severity used for escalation and triage.",
        examples=["high"],
    )
    portfolio_id: str | None = Field(
        default=None,
        description="Portfolio affected by the finding when the control is portfolio-scoped.",
        examples=["PORT-OPS-001"],
    )
    security_id: str | None = Field(
        default=None,
        description="Security identifier affected by the finding when instrument scope exists.",
        examples=["SEC-US-IBM"],
    )
    transaction_id: str | None = Field(
        default=None,
        description="Transaction identifier affected by the finding when transaction scope exists.",
        examples=["TXN-20260306-0142"],
    )
    business_date: date | None = Field(
        default=None,
        description="Business date evaluated by the control for this finding.",
        examples=["2026-03-06"],
    )
    epoch: int | None = Field(
        default=None,
        description="Epoch evaluated by the control for this finding.",
        examples=[0],
    )
    expected_value: dict[str, Any] | None = Field(
        default=None,
        description="Expected control-side value used for comparison.",
        examples=[{"cashflow_count": 1}],
    )
    observed_value: dict[str, Any] | None = Field(
        default=None,
        description="Observed persisted value found in the underlying tables.",
        examples=[{"cashflow_count": 0}],
    )
    detail: dict[str, Any] | None = Field(
        default=None,
        description="Additional structured detail describing the mismatch or control breach.",
        examples=[
            {
                "rule_transaction_type": "BUY",
                "reason": "Transaction has a cashflow rule but no persisted cashflow row.",
            }
        ],
    )
    created_at: datetime = Field(
        description="UTC timestamp when the finding was persisted.",
        examples=["2026-03-06T14:03:11Z"],
    )


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
    run_id: str = Field(
        description="Unique reconciliation run identifier.",
        examples=["FRR-20260306-0001"],
    )
    reconciliation_type: ReconciliationType = Field(
        description="Control family executed by this run.",
        examples=["transaction_cashflow"],
    )
    portfolio_id: str | None = Field(
        default=None,
        description="Portfolio scope for the run when the request is portfolio-specific.",
        examples=["PORT-OPS-001"],
    )
    business_date: date | None = Field(
        default=None,
        description="Business date scope for the run when supplied.",
        examples=["2026-03-06"],
    )
    epoch: int | None = Field(
        default=None,
        description="Epoch scope for the run when supplied.",
        examples=[0],
    )
    status: str = Field(
        description="Lifecycle status of the run.",
        examples=["completed"],
    )
    requested_by: str | None = Field(
        default=None,
        description="Actor or scheduler identity that requested the run.",
        examples=["ops_control_plane"],
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation identifier propagated across control-plane workflows.",
        examples=["CTL:9b4db9d1-1a39-42f2-9f55-2b2a4f9a4700"],
    )
    tolerance: Decimal | None = Field(
        default=None,
        description="Tolerance applied by the control for value comparisons.",
        examples=["0.01"],
    )
    summary: dict[str, Any] | None = Field(
        default=None,
        description="Structured summary of checked records, findings, and pass/fail outcome.",
        examples=[{"checked_transactions": 142, "finding_count": 1, "passed": False}],
    )
    failure_reason: str | None = Field(
        default=None,
        description="Failure reason when the control run does not complete successfully.",
        examples=[None],
    )
    started_at: datetime = Field(
        description="UTC timestamp when run execution started.",
        examples=["2026-03-06T14:03:10Z"],
    )
    completed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when run execution completed, if completed.",
        examples=["2026-03-06T14:03:11Z"],
    )
    created_at: datetime = Field(
        description="UTC timestamp when the run record was created.",
        examples=["2026-03-06T14:03:10Z"],
    )
    updated_at: datetime = Field(
        description="UTC timestamp when the run record was last updated.",
        examples=["2026-03-06T14:03:11Z"],
    )


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
    runs: list[ReconciliationRunResponse] = Field(
        description="Reconciliation runs matching the requested filters.",
    )
    total: int = Field(
        description="Total number of runs returned in this response.",
        examples=[1],
    )


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
    findings: list[ReconciliationFindingResponse] = Field(
        description="Findings captured for the requested reconciliation run.",
    )
    total: int = Field(
        description="Total number of findings returned in this response.",
        examples=[1],
    )
