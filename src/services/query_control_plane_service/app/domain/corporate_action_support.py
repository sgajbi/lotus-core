"""Persistence-independent corporate-action operational evidence."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CorporateActionManifestEvidence:
    manifest_version: int
    corporate_action_type: str
    completion_declared: bool
    expected_node_count: int
    expected_edge_count: int
    opened_observation_sequence: int
    source_system: str
    source_record_id: str
    source_revision: str
    source_content_hash: str
    manifest_content_hash: str
    source_observed_at: datetime


@dataclass(frozen=True, slots=True)
class CorporateActionReadinessEvidence:
    through_observation_sequence: int
    manifest_content_hash: str | None
    execution_plan_content_hash: str | None
    ordered_member_count: int
    finding_reason_codes: tuple[str, ...]
    correlation_id: str | None
    evaluated_at: datetime


@dataclass(frozen=True, slots=True)
class CorporateActionExecutionReleaseEvidence:
    release_id: int
    release_authority_hash: str
    status: str
    member_count: int
    completed_member_count: int
    attempt_count: int
    fence_token: int
    lease_state: str
    lease_expires_at: datetime | None
    terminal_reason_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class CorporateActionEventEvidence:
    corporate_action_event_id: str
    linked_transaction_group_id: str
    parent_event_reference: str
    state_version: int
    current_manifest_version: int | None
    readiness_status: str
    last_observation_sequence: int
    event_created_at: datetime
    event_updated_at: datetime
    current_manifest: CorporateActionManifestEvidence | None
    readiness: CorporateActionReadinessEvidence
    execution_release: CorporateActionExecutionReleaseEvidence | None


@dataclass(frozen=True, slots=True)
class CorporateActionEventEvidencePage:
    total: int
    items: tuple[CorporateActionEventEvidence, ...]
