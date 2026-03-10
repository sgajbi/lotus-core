# services/query-service/app/dtos/simulation_dto.py
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SimulationSessionCreateRequest(BaseModel):
    portfolio_id: str = Field(
        ...,
        min_length=1,
        description="Portfolio identifier for the simulated scenario.",
        examples=["PORT-SIM-001"],
    )
    created_by: str | None = Field(
        default=None,
        description="Operator or workflow identity creating the simulation session.",
        examples=["ops.user@lotus"],
    )
    ttl_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Session time-to-live in hours before the simulation expires automatically.",
        examples=[24],
    )


class SimulationSessionRecord(BaseModel):
    session_id: str = Field(
        description="Stable simulation session identifier.",
        examples=["SIM-20260310-0001"],
    )
    portfolio_id: str = Field(
        description="Portfolio identifier associated with the simulation session.",
        examples=["PORT-SIM-001"],
    )
    status: str = Field(
        description="Lifecycle status of the simulation session.",
        examples=["ACTIVE"],
    )
    version: int = Field(
        description="Monotonic version incremented when simulation changes are modified.",
        examples=[3],
    )
    created_by: str | None = Field(
        default=None,
        description="Identity that created the simulation session.",
        examples=["ops.user@lotus"],
    )
    created_at: datetime = Field(
        description="UTC timestamp when the session was created.",
        examples=["2026-03-10T08:15:00Z"],
    )
    expires_at: datetime = Field(
        description="UTC timestamp when the session expires and becomes inactive.",
        examples=["2026-03-11T08:15:00Z"],
    )

    model_config = ConfigDict(from_attributes=True)


class SimulationSessionResponse(BaseModel):
    session: SimulationSessionRecord = Field(
        description="Simulation session metadata.",
    )


class SimulationChangeInput(BaseModel):
    security_id: str = Field(
        ...,
        min_length=1,
        description="Security identifier affected by the proposed simulation change.",
        examples=["SEC-US-IBM"],
    )
    transaction_type: str = Field(
        ...,
        min_length=1,
        description="Transaction type used to derive the position impact of the proposed change.",
        examples=["BUY"],
    )
    quantity: float | None = Field(
        default=None,
        description="Transaction quantity used for quantity-driven changes.",
        examples=[100.0],
    )
    price: float | None = Field(
        default=None,
        description="Unit price associated with the simulated transaction, when relevant.",
        examples=[127.45],
    )
    amount: float | None = Field(
        default=None,
        description="Cash amount associated with the simulated transaction, when relevant.",
        examples=[12745.0],
    )
    currency: str | None = Field(
        default=None,
        description="Currency of the proposed price or amount.",
        examples=["USD"],
    )
    effective_date: date | None = Field(
        default=None,
        description="Business-effective date to apply for the simulation change.",
        examples=["2026-03-10"],
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Additional scenario metadata preserved with the simulated change.",
        examples=[{"source": "manual-what-if", "note": "defensive rebalance"}],
    )


class SimulationChangeUpsertRequest(BaseModel):
    changes: list[SimulationChangeInput] = Field(
        default_factory=list,
        description="Ordered set of simulation changes to add or replace in the session.",
    )


class SimulationChangeRecord(BaseModel):
    change_id: str = Field(
        description="Stable identifier for the simulation change record.",
        examples=["SIM-CHG-0001"],
    )
    session_id: str = Field(
        description="Simulation session identifier that owns the change.",
        examples=["SIM-20260310-0001"],
    )
    portfolio_id: str = Field(
        description="Portfolio identifier affected by the simulation change.",
        examples=["PORT-SIM-001"],
    )
    security_id: str = Field(
        description="Security identifier affected by the simulation change.",
        examples=["SEC-US-IBM"],
    )
    transaction_type: str = Field(
        description="Transaction type used to derive the projected position effect.",
        examples=["BUY"],
    )
    quantity: float | None = Field(
        default=None,
        description="Projected transaction quantity.",
        examples=[100.0],
    )
    price: float | None = Field(
        default=None,
        description="Projected transaction unit price.",
        examples=[127.45],
    )
    amount: float | None = Field(
        default=None,
        description="Projected transaction cash amount.",
        examples=[12745.0],
    )
    currency: str | None = Field(
        default=None,
        description="Currency of the projected price or amount.",
        examples=["USD"],
    )
    effective_date: date | None = Field(
        default=None,
        description="Business-effective date used when the change is applied.",
        examples=["2026-03-10"],
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Scenario metadata associated with the simulation change.",
        examples=[{"source": "manual-what-if", "note": "defensive rebalance"}],
    )
    created_at: datetime = Field(
        description="UTC timestamp when the simulation change was recorded.",
        examples=["2026-03-10T08:20:00Z"],
    )

    model_config = ConfigDict(from_attributes=True)


class SimulationChangesResponse(BaseModel):
    session_id: str = Field(
        description="Simulation session identifier that owns the returned changes.",
        examples=["SIM-20260310-0001"],
    )
    version: int = Field(
        description="Current simulation session version after the change mutation.",
        examples=[4],
    )
    changes: list[SimulationChangeRecord] = Field(
        description="Current ordered set of simulation changes recorded for the session.",
    )


class ProjectedPositionRecord(BaseModel):
    security_id: str = Field(
        description="Security identifier for the projected position.",
        examples=["SEC-US-IBM"],
    )
    instrument_name: str = Field(
        description="Human-readable instrument name.",
        examples=["IBM Common Stock"],
    )
    asset_class: str | None = Field(
        default=None,
        description="Asset class of the projected position.",
        examples=["Equity"],
    )
    baseline_quantity: float = Field(
        description="Current baseline position quantity before simulation changes.",
        examples=[250.0],
    )
    proposed_quantity: float = Field(
        description="Projected quantity after applying all simulation changes.",
        examples=[350.0],
    )
    delta_quantity: float = Field(
        description="Net quantity change introduced by the simulation.",
        examples=[100.0],
    )
    cost_basis: float | None = Field(
        default=None,
        description="Current baseline cost basis in portfolio reporting currency.",
        examples=[28500.0],
    )
    cost_basis_local: float | None = Field(
        default=None,
        description="Current baseline cost basis in local instrument currency.",
        examples=[28500.0],
    )


class ProjectedPositionsResponse(BaseModel):
    session_id: str = Field(
        description="Simulation session identifier used for the projection.",
        examples=["SIM-20260310-0001"],
    )
    portfolio_id: str = Field(
        description="Portfolio identifier used for the projection.",
        examples=["PORT-SIM-001"],
    )
    baseline_as_of: date | None = Field(
        default=None,
        description="Business date of the baseline position set used for projection.",
        examples=["2026-03-10"],
    )
    positions: list[ProjectedPositionRecord] = Field(
        description="Projected positions after all simulation changes are applied.",
    )


class ProjectedSummaryResponse(BaseModel):
    session_id: str = Field(
        description="Simulation session identifier used for the summary.",
        examples=["SIM-20260310-0001"],
    )
    portfolio_id: str = Field(
        description="Portfolio identifier used for the summary.",
        examples=["PORT-SIM-001"],
    )
    total_baseline_positions: int = Field(
        description="Count of baseline positions retained in the projection.",
        examples=[12],
    )
    total_proposed_positions: int = Field(
        description="Count of projected positions after applying simulation changes.",
        examples=[13],
    )
    net_delta_quantity: float = Field(
        description="Net quantity delta across all projected positions.",
        examples=[150.0],
    )
