"""Bounded operator contracts for corporate-action readiness and release support."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CorporateActionManifestSupport(BaseModel):
    manifest_version: int = Field(..., ge=1)
    corporate_action_type: str
    completion_declared: bool
    expected_node_count: int = Field(..., ge=0)
    expected_edge_count: int = Field(..., ge=0)
    opened_observation_sequence: int = Field(..., ge=0)
    source_system: str
    source_record_id: str
    source_revision: str
    source_content_hash: str
    manifest_content_hash: str
    source_observed_at: datetime


class CorporateActionReadinessSupport(BaseModel):
    through_observation_sequence: int = Field(..., ge=0)
    manifest_content_hash: str | None = None
    execution_plan_content_hash: str | None = None
    ordered_member_count: int = Field(..., ge=0)
    finding_count: int = Field(..., ge=0)
    finding_reason_codes: list[str]
    correlation_id: str | None = None
    evaluated_at: datetime


class CorporateActionExecutionReleaseSupport(BaseModel):
    release_id: int = Field(..., ge=1)
    release_authority_hash: str
    status: Literal["PENDING", "PROCESSING", "COMPLETE", "FAILED", "SUPERSEDED"]
    member_count: int = Field(..., ge=1)
    completed_member_count: int = Field(..., ge=0)
    attempt_count: int = Field(..., ge=0)
    fence_token: int = Field(..., ge=0)
    lease_state: Literal["NONE", "ACTIVE", "EXPIRED"]
    lease_expires_at: datetime | None = None
    terminal_reason_code: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class CorporateActionEventSupportItem(BaseModel):
    corporate_action_event_id: str
    linked_transaction_group_id: str
    parent_event_reference: str
    state_version: int = Field(..., ge=0)
    current_manifest_version: int | None = Field(None, ge=1)
    readiness_status: Literal[
        "AWAITING_MANIFEST",
        "AWAITING_COMPLETION",
        "AWAITING_CHILDREN",
        "INVALID",
        "READY",
    ]
    last_observation_sequence: int = Field(..., ge=0)
    event_created_at: datetime
    event_updated_at: datetime
    current_manifest: CorporateActionManifestSupport | None = None
    readiness: CorporateActionReadinessSupport
    execution_release: CorporateActionExecutionReleaseSupport | None = None


class CorporateActionEventSupportListResponse(BaseModel):
    tenant_id: str
    legal_book_id: str
    portfolio_id: str
    generated_at_utc: datetime
    total: int = Field(..., ge=0)
    skip: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=100)
    items: list[CorporateActionEventSupportItem]
