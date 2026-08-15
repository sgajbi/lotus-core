"""Tenant-bound application service for security-audit support queries."""

from __future__ import annotations

from datetime import datetime

from portfolio_common.domain.security_audit import (
    SecurityAuditComponent,
    SecurityAuditDecision,
    SecurityAuditPage,
    SecurityAuditQuery,
)
from portfolio_common.ports.security_audit import SecurityAuditStore


class InvalidSecurityAuditQuery(ValueError):
    """Caller-supplied security-audit query parameters violate domain bounds."""


class SecurityAuditQueryService:
    def __init__(self, store: SecurityAuditStore) -> None:
        self._store = store

    async def list_events(
        self,
        *,
        tenant_id: str,
        occurred_from: datetime,
        occurred_to: datetime,
        page_size: int,
        cursor_occurred_at: datetime | None,
        cursor_event_id: str | None,
        component: SecurityAuditComponent | None,
        decision: SecurityAuditDecision | None,
    ) -> SecurityAuditPage:
        try:
            query = SecurityAuditQuery(
                tenant_id=tenant_id,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
                page_size=page_size,
                cursor_occurred_at=cursor_occurred_at,
                cursor_event_id=cursor_event_id,
                component=component,
                decision=decision,
            )
        except ValueError as exc:
            raise InvalidSecurityAuditQuery from exc

        page: SecurityAuditPage = await self._store.query(query)
        return page
