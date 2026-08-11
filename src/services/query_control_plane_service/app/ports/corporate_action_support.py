"""Read port for bounded corporate-action operational evidence."""

from typing import Protocol

from ..domain.corporate_action_support import CorporateActionEventEvidencePage


class CorporateActionSupportReader(Protocol):
    async def list_current(
        self,
        *,
        tenant_id: str,
        legal_book_id: str,
        portfolio_id: str,
        corporate_action_event_id: str | None,
        readiness_status: str | None,
        execution_status: str | None,
        skip: int,
        limit: int,
    ) -> CorporateActionEventEvidencePage: ...
