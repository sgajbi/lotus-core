"""Domain contract for durable enterprise access-decision evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

SECURITY_AUDIT_SCHEMA_VERSION = "1.0"
OPERATIONAL_SECURITY_AUDIT_CLASSIFICATION = "operational_security_audit"


class SecurityAuditComponent(StrEnum):
    INGESTION = "ingestion_service"
    QUERY = "query_service"
    QUERY_CONTROL_PLANE = "query_control_plane_service"
    FINANCIAL_RECONCILIATION = "financial_reconciliation_service"
    EVENT_REPLAY = "event_replay_service"


class SecurityAuditDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class SecurityAuditReason(StrEnum):
    AUTHORIZED = "authorized"
    AUTHORIZATION_POLICY_DENIED = "authorization_policy_denied"
    PAYLOAD_TOO_LARGE = "payload_too_large"


class SecurityAuditIdentityPosture(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class SecurityAuditMethod(StrEnum):
    GET = "GET"
    HEAD = "HEAD"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


@dataclass(frozen=True, slots=True)
class SecurityAuditEvent:
    """One append-only decision made before protected HTTP work executes."""

    event_id: str
    occurred_at: datetime
    component: SecurityAuditComponent
    route_template: str
    method: SecurityAuditMethod
    decision: SecurityAuditDecision
    reason: SecurityAuditReason
    required_capability: str | None
    service_identity: str | None
    actor_id: str | None
    tenant_id: str | None
    role: str | None
    identity_posture: SecurityAuditIdentityPosture
    correlation_id: str | None
    trace_id: str | None
    policy_version: str
    schema_version: str = SECURITY_AUDIT_SCHEMA_VERSION
    classification: str = OPERATIONAL_SECURITY_AUDIT_CLASSIFICATION

    def __post_init__(self) -> None:
        _require_uuid(self.event_id)
        _require_aware_time(self.occurred_at)
        _require_route_template(self.route_template)
        _require_text("policy_version", self.policy_version, maximum=64)
        _require_optional_text("required_capability", self.required_capability, maximum=128)
        _require_optional_text("service_identity", self.service_identity, maximum=128)
        _require_optional_text("actor_id", self.actor_id, maximum=128)
        _require_optional_text("tenant_id", self.tenant_id, maximum=128)
        _require_optional_text("role", self.role, maximum=128)
        _require_optional_text("correlation_id", self.correlation_id, maximum=128)
        _require_optional_text("trace_id", self.trace_id, maximum=128)
        if self.schema_version != SECURITY_AUDIT_SCHEMA_VERSION:
            raise ValueError("unsupported security-audit schema version")
        if self.classification != OPERATIONAL_SECURITY_AUDIT_CLASSIFICATION:
            raise ValueError("unsupported security-audit classification")
        _validate_identity_posture(self)


@dataclass(frozen=True, slots=True)
class SecurityAuditQuery:
    tenant_id: str
    occurred_from: datetime
    occurred_to: datetime
    page_size: int
    cursor_occurred_at: datetime | None = None
    cursor_event_id: str | None = None
    component: SecurityAuditComponent | None = None
    decision: SecurityAuditDecision | None = None

    def __post_init__(self) -> None:
        _require_text("tenant_id", self.tenant_id, maximum=128)
        _require_aware_time(self.occurred_from)
        _require_aware_time(self.occurred_to)
        if self.occurred_from > self.occurred_to:
            raise ValueError("security-audit time range is inverted")
        if not 1 <= self.page_size <= 200:
            raise ValueError("security-audit page size must be between 1 and 200")
        if (self.cursor_occurred_at is None) != (self.cursor_event_id is None):
            raise ValueError("security-audit cursor fields must be supplied together")
        if self.cursor_occurred_at is not None:
            _require_aware_time(self.cursor_occurred_at)
        if self.cursor_event_id is not None:
            _require_uuid(self.cursor_event_id)


@dataclass(frozen=True, slots=True)
class SecurityAuditPage:
    events: tuple[SecurityAuditEvent, ...]
    next_cursor_occurred_at: datetime | None
    next_cursor_event_id: str | None

    def __post_init__(self) -> None:
        if (self.next_cursor_occurred_at is None) != (self.next_cursor_event_id is None):
            raise ValueError("security-audit next cursor fields must be supplied together")
        if self.next_cursor_occurred_at is not None:
            _require_aware_time(self.next_cursor_occurred_at)
        if self.next_cursor_event_id is not None:
            _require_uuid(self.next_cursor_event_id)


def _validate_identity_posture(event: SecurityAuditEvent) -> None:
    authoritative_fields = (
        event.service_identity,
        event.actor_id,
        event.tenant_id,
        event.role,
    )
    if event.identity_posture is SecurityAuditIdentityPosture.VERIFIED and any(
        value is None for value in authoritative_fields
    ):
        raise ValueError("verified security-audit identity requires all identity fields")
    if event.identity_posture is SecurityAuditIdentityPosture.UNVERIFIED and any(
        value is not None for value in authoritative_fields
    ):
        raise ValueError("unverified security-audit identity cannot carry authority fields")


def _require_uuid(value: str) -> None:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("security-audit event id must be a UUID") from exc
    if str(parsed) != value.lower():
        raise ValueError("security-audit event id must use canonical UUID text")


def _require_aware_time(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("security-audit timestamps must be timezone-aware")


def _require_route_template(value: str) -> None:
    _require_text("route_template", value, maximum=256)
    if not value.startswith("/"):
        raise ValueError("security-audit route template must be absolute")
    if "?" in value or "#" in value or "://" in value:
        raise ValueError("security-audit route template cannot contain request-specific data")


def _require_optional_text(name: str, value: str | None, *, maximum: int) -> None:
    if value is not None:
        _require_text(name, value, maximum=maximum)


def _require_text(name: str, value: str, *, maximum: int) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{name} must be non-blank normalized text")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
