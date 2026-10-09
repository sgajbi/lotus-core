"""Acknowledge retained scoped FX authority without mutating legacy valuation rates."""

from portfolio_common.fx_source_events import FxSourceCutPersistedEvent
from portfolio_common.fx_source_models import FxRateSourceCut
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def acknowledge_retained_fx_cut(
    db: AsyncSession, event: FxSourceCutPersistedEvent, *, correlation_id: str
) -> bool:
    """Verify the durable source before fencing a notification in the caller's UOW.

    A scoped cut is not a tenantless FxRateCorrection. The legacy valuation flow
    deliberately receives no jobs or projection writes from this notification.
    Qualified consumers resolve the retained cut through the source read contract.
    """
    row = await db.scalar(
        select(FxRateSourceCut).where(
            FxRateSourceCut.cut_id == event.cut_id,
            FxRateSourceCut.tenant_id == event.tenant_id,
            FxRateSourceCut.provider_id == event.provider_id,
            FxRateSourceCut.source_id == event.source_id,
        )
    )
    expected_members = [member.model_dump(mode="json") for member in event.members]
    if row is None or (
        row.content_hash != event.content_hash
        or row.member_count != event.member_count
        or row.members != expected_members
        or row.accepted_at != event.accepted_at
        or row.source_observed_cutoff != event.source_observed_cutoff
    ):
        raise ValueError("FX_SOURCE_PERSISTED_NOTIFICATION_MISMATCH")
    claimed: bool = await IdempotencyRepository(db).claim_event_processing(
        event.cut_id,
        "N/A",
        "fx-source-cut-retained-notification",
        correlation_id,
        tenant_id=event.tenant_id,
    )
    return claimed
