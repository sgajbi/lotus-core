"""Application port for durable enterprise security-audit evidence."""

from __future__ import annotations

from typing import Protocol

from portfolio_common.domain.security_audit import (
    SecurityAuditEvent,
    SecurityAuditPage,
    SecurityAuditQuery,
)


class SecurityAuditStore(Protocol):
    async def append(self, event: SecurityAuditEvent) -> None:
        """Durably append one access decision or raise a safe infrastructure error."""

    async def query(self, query: SecurityAuditQuery) -> SecurityAuditPage:
        """Return a tenant-bound, keyset-paginated page of audit evidence."""
