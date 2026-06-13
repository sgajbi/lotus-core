from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class IngestionCapacityGroupResponse(BaseModel):
    endpoint: str = Field(
        description="Ingestion endpoint associated with this capacity group.",
        examples=["/ingest/transactions"],
    )
    entity_type: str = Field(
        description="Canonical entity type associated with this capacity group.",
        examples=["transaction"],
    )
    total_records: int = Field(
        ge=0,
        description="Total accepted records observed in the lookback window for this group.",
        examples=[25000],
    )
    processed_records: int = Field(
        ge=0,
        description=(
            "Records in this group that progressed out of accepted state (queued or failed)."
        ),
        examples=[24000],
    )
    backlog_records: int = Field(
        ge=0,
        description="Records still pending processing in accepted state.",
        examples=[1000],
    )
    backlog_jobs: int = Field(
        ge=0,
        description="Pending job count in accepted state for this group.",
        examples=[12],
    )
    lambda_in_events_per_second: Decimal = Field(
        ge=Decimal("0"),
        description="Inbound record rate (`lambda_in`) for this group over the lookback window.",
        examples=["6.944444"],
    )
    mu_msg_per_replica_events_per_second: Decimal = Field(
        ge=Decimal("0"),
        description="Estimated per-replica processing rate (`mu_msg`) for this group.",
        examples=["6.666667"],
    )
    assumed_replicas: int = Field(
        ge=1,
        description="Replica count assumed for effective-capacity and utilization calculations.",
        examples=[2],
    )
    effective_capacity_events_per_second: Decimal = Field(
        ge=Decimal("0"),
        description="Estimated effective capacity (`N_replica * mu_msg`) for this group.",
        examples=["13.333334"],
    )
    utilization_ratio: Decimal = Field(
        ge=Decimal("0"),
        description=(
            "Utilization ratio (`rho = lambda_in / capacity`). Values above 1 indicate overload."
        ),
        examples=["0.520833"],
    )
    headroom_ratio: Decimal = Field(
        description=(
            "Capacity headroom ratio (`1 - rho`). Negative values indicate sustained overload."
        ),
        examples=["0.479167"],
    )
    estimated_drain_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Estimated backlog drain time in seconds using "
            "`T_drain = backlog / (capacity - lambda_in)` "
            "when net drain capacity is positive."
        ),
        examples=[300.0],
    )
    saturation_state: Literal["stable", "near_capacity", "over_capacity"] = Field(
        description="Operational saturation classification derived from utilization ratio bands.",
        examples=["stable"],
    )


class IngestionCapacityStatusResponse(BaseModel):
    as_of: datetime = Field(
        description="UTC timestamp when capacity status was computed.",
        examples=["2026-03-03T14:55:22.000Z"],
    )
    lookback_minutes: int = Field(
        ge=1,
        description="Lookback window in minutes used for capacity calculations.",
        examples=[60],
    )
    assumed_replicas: int = Field(
        ge=1,
        description="Replica count assumption used for all capacity rows in this response.",
        examples=[2],
    )
    total_backlog_records: int = Field(
        ge=0,
        description="Total accepted-state backlog records across all returned groups.",
        examples=[4200],
    )
    total_groups: int = Field(
        ge=0,
        description="Number of capacity groups returned in this response.",
        examples=[5],
    )
    groups: list[IngestionCapacityGroupResponse] = Field(
        description="Per endpoint/entity capacity diagnostics sorted by highest backlog pressure."
    )


class IngestionBacklogBreakdownItemResponse(BaseModel):
    endpoint: str = Field(
        description="Ingestion endpoint associated with this backlog group.",
        examples=["/ingest/transactions"],
    )
    entity_type: str = Field(
        description="Canonical entity type associated with this backlog group.",
        examples=["transaction"],
    )
    total_jobs: int = Field(
        ge=0,
        description="Total jobs observed for this endpoint/entity group in lookback window.",
        examples=[1250],
    )
    accepted_jobs: int = Field(
        ge=0,
        description="Accepted jobs for this endpoint/entity group.",
        examples=[2],
    )
    queued_jobs: int = Field(
        ge=0,
        description="Queued jobs for this endpoint/entity group.",
        examples=[5],
    )
    failed_jobs: int = Field(
        ge=0,
        description="Failed jobs for this endpoint/entity group.",
        examples=[7],
    )
    backlog_jobs: int = Field(
        ge=0,
        description="Backlog count (accepted + queued) for this endpoint/entity group.",
        examples=[7],
    )
    oldest_backlog_submitted_at: datetime | None = Field(
        default=None,
        description="Submitted timestamp of oldest non-terminal job in this group.",
        examples=["2026-03-01T01:05:12.120Z"],
    )
    oldest_backlog_age_seconds: float = Field(
        ge=0.0,
        description="Age in seconds of oldest non-terminal job in this group.",
        examples=[182.4],
    )
    failure_rate: Decimal = Field(
        ge=Decimal("0"),
        description="Failed jobs divided by total jobs for this group.",
        examples=["0.0056"],
    )


class IngestionBacklogBreakdownResponse(BaseModel):
    lookback_minutes: int = Field(
        ge=1,
        description="Lookback window in minutes used to build backlog breakdown.",
        examples=[1440],
    )
    total_backlog_jobs: int = Field(
        ge=0,
        description="Total backlog jobs across all returned groups.",
        examples=[17],
    )
    largest_group_backlog_jobs: int = Field(
        ge=0,
        description="Backlog jobs in the largest endpoint/entity backlog group.",
        examples=[9],
    )
    largest_group_backlog_share: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("1"),
        description=(
            "Largest-group backlog concentration share "
            "(largest_group_backlog_jobs / total_backlog_jobs)."
        ),
        examples=["0.5294"],
    )
    top_3_backlog_share: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("1"),
        description="Backlog concentration share of the top 3 groups by backlog_jobs.",
        examples=["0.8824"],
    )
    groups: list[IngestionBacklogBreakdownItemResponse] = Field(
        description="Backlog and failure-rate breakdown grouped by endpoint and entity_type."
    )
