from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from portfolio_common.domain.security_audit import (
    OPERATIONAL_SECURITY_AUDIT_CLASSIFICATION,
    SECURITY_AUDIT_SCHEMA_VERSION,
    SecurityAuditComponent,
    SecurityAuditDecision,
    SecurityAuditEvent,
    SecurityAuditIdentityPosture,
    SecurityAuditMethod,
    SecurityAuditPage,
    SecurityAuditQuery,
    SecurityAuditReason,
)

EVENT_ID = "7ed85e15-27d2-4650-bab0-8f8c87042bd7"
EVENT_TIME = datetime(2026, 8, 15, 1, 2, 3, tzinfo=timezone.utc)


def _verified_event() -> SecurityAuditEvent:
    return SecurityAuditEvent(
        event_id=EVENT_ID,
        occurred_at=EVENT_TIME,
        component=SecurityAuditComponent.QUERY_CONTROL_PLANE,
        route_template="/support/security-audit/events",
        method=SecurityAuditMethod.GET,
        decision=SecurityAuditDecision.ALLOW,
        reason=SecurityAuditReason.AUTHORIZED,
        required_capability="core.security_audit.read",
        service_identity="lotus-gateway",
        actor_id="operations-user-1",
        tenant_id="tenant-sg-1",
        role="operations_support",
        identity_posture=SecurityAuditIdentityPosture.VERIFIED,
        correlation_id="QCP-123",
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        policy_version="1.0.0",
    )


def test_security_audit_event_accepts_closed_source_safe_evidence() -> None:
    event = _verified_event()

    assert event.schema_version == SECURITY_AUDIT_SCHEMA_VERSION
    assert event.classification == OPERATIONAL_SECURITY_AUDIT_CLASSIFICATION
    assert event.tenant_id == "tenant-sg-1"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"route_template": "/clients/CIF-123?token=secret"}, "request-specific data"),
        ({"route_template": "support/events"}, "must be absolute"),
        ({"event_id": "not-an-id"}, "must be a UUID"),
        ({"occurred_at": datetime(2026, 8, 15)}, "timezone-aware"),
        ({"policy_version": " "}, "non-blank normalized text"),
        ({"schema_version": "2.0"}, "unsupported security-audit schema version"),
        ({"classification": "business_data"}, "unsupported security-audit classification"),
    ],
)
def test_security_audit_event_rejects_unbounded_or_unsafe_evidence(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_verified_event(), **changes)


def test_unverified_identity_cannot_fabricate_authority() -> None:
    with pytest.raises(ValueError, match="cannot carry authority fields"):
        replace(
            _verified_event(),
            identity_posture=SecurityAuditIdentityPosture.UNVERIFIED,
        )


def test_verified_identity_requires_complete_authority() -> None:
    with pytest.raises(ValueError, match="requires all identity fields"):
        replace(_verified_event(), tenant_id=None)


def test_unverified_denial_preserves_absence_without_placeholders() -> None:
    event = replace(
        _verified_event(),
        decision=SecurityAuditDecision.DENY,
        reason=SecurityAuditReason.AUTHORIZATION_POLICY_DENIED,
        required_capability=None,
        service_identity=None,
        actor_id=None,
        tenant_id=None,
        role=None,
        identity_posture=SecurityAuditIdentityPosture.UNVERIFIED,
    )

    assert event.service_identity is None
    assert event.actor_id is None
    assert event.tenant_id is None
    assert event.role is None


def test_security_audit_query_requires_bounded_tenant_keyset_scope() -> None:
    query = SecurityAuditQuery(
        tenant_id="tenant-sg-1",
        occurred_from=EVENT_TIME,
        occurred_to=EVENT_TIME,
        page_size=100,
        cursor_occurred_at=EVENT_TIME,
        cursor_event_id=EVENT_ID,
        component=SecurityAuditComponent.QUERY,
        decision=SecurityAuditDecision.DENY,
    )

    assert query.page_size == 100
    assert query.cursor_event_id == EVENT_ID


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"tenant_id": ""}, "non-blank normalized text"),
        ({"page_size": 0}, "between 1 and 200"),
        ({"page_size": 201}, "between 1 and 200"),
        ({"occurred_from": datetime(2026, 8, 16, tzinfo=timezone.utc)}, "inverted"),
        ({"occurred_to": EVENT_TIME + timedelta(days=31, seconds=1)}, "cannot exceed 31 days"),
        ({"cursor_event_id": EVENT_ID}, "must be supplied together"),
    ],
)
def test_security_audit_query_rejects_unbounded_or_incomplete_scope(
    changes: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "tenant_id": "tenant-sg-1",
        "occurred_from": EVENT_TIME,
        "occurred_to": datetime(2026, 8, 15, 2, tzinfo=timezone.utc),
        "page_size": 100,
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        SecurityAuditQuery(**values)  # type: ignore[arg-type]


def test_security_audit_page_requires_complete_next_cursor() -> None:
    with pytest.raises(ValueError, match="must be supplied together"):
        SecurityAuditPage(
            events=(_verified_event(),),
            next_cursor_occurred_at=EVENT_TIME,
            next_cursor_event_id=None,
        )
