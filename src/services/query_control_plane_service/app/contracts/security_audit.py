"""Public support contract for durable enterprise security-audit evidence."""

from __future__ import annotations

from datetime import datetime

from portfolio_common.domain.security_audit import (
    SecurityAuditComponent,
    SecurityAuditDecision,
    SecurityAuditIdentityPosture,
    SecurityAuditMethod,
    SecurityAuditReason,
)
from pydantic import BaseModel, ConfigDict, Field


class SecurityAuditEventResponse(BaseModel):
    """Source-safe access-decision evidence; request content is intentionally absent."""

    model_config = ConfigDict(from_attributes=True)

    event_id: str = Field(description="Canonical UUID for the append-only audit event.")
    occurred_at: datetime = Field(description="UTC decision timestamp recorded before execution.")
    component: SecurityAuditComponent
    route_template: str = Field(
        description="Governed route template; never a concrete request URL or query string."
    )
    method: SecurityAuditMethod
    decision: SecurityAuditDecision
    reason: SecurityAuditReason
    required_capability: str | None = None
    service_identity: str | None = Field(
        default=None,
        description="Verified calling service identity; null when identity is unverified.",
    )
    actor_id: str | None = None
    tenant_id: str | None = None
    role: str | None = None
    identity_posture: SecurityAuditIdentityPosture
    correlation_id: str | None = None
    trace_id: str | None = None
    policy_version: str
    schema_version: str
    classification: str


class SecurityAuditPageResponse(BaseModel):
    events: list[SecurityAuditEventResponse]
    next_cursor_occurred_at: datetime | None = None
    next_cursor_event_id: str | None = None
