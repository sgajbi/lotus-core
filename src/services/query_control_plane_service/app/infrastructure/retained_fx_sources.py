"""Read retained source revisions at distinct source-observed and Core-known instants."""

from datetime import date

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.fx_source_models import FxRateSourceCut, FxRateSourceRevision
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..domain.market_fx import (
    FxRateEvidence,
    FxRateSourceEvidence,
    FxSourceSelection,
    FxSourceSelectionRejected,
)


def _visible(model, selection: FxSourceSelection) -> tuple:
    scope = selection.scope
    return (
        model.tenant_id == scope.tenant_id,
        model.provider_id == scope.provider_id,
        model.source_id == scope.source_id,
        model.source_observed_at <= selection.source_as_of,
        model.accepted_at <= selection.known_as_of,
    )


async def read_retained_fx_rates(
    session: AsyncSession,
    *,
    selection: FxSourceSelection,
    from_currency: str,
    to_currency: str,
    start_date: date,
    end_date: date,
) -> list[FxRateEvidence]:
    """Fixed cuts resolve exact immutable membership; as-of mode resolves visible heads.

    Provider and source are mandatory, never ranked by caller timestamps. More
    than one independent chain for the same pair/date is a conflict, not a choice.
    A correction unknown at the requested knowledge instant cannot hide its parent.
    """
    statement = select(FxRateSourceRevision).where(
        *_visible(FxRateSourceRevision, selection),
        FxRateSourceRevision.from_currency == normalize_currency_code(from_currency),
        FxRateSourceRevision.to_currency == normalize_currency_code(to_currency),
        FxRateSourceRevision.rate_date >= start_date,
        FxRateSourceRevision.rate_date <= end_date,
    )
    member_hashes = None
    if selection.cut_id is not None:
        scope = selection.scope
        cut = await session.scalar(
            select(FxRateSourceCut).where(
                FxRateSourceCut.cut_id == selection.cut_id,
                FxRateSourceCut.tenant_id == scope.tenant_id,
                FxRateSourceCut.provider_id == scope.provider_id,
                FxRateSourceCut.source_id == scope.source_id,
                FxRateSourceCut.source_observed_cutoff <= selection.source_as_of,
                FxRateSourceCut.accepted_at <= selection.known_as_of,
            )
        )
        if cut is None:
            raise FxSourceSelectionRejected("FX_SOURCE_CUT_UNAVAILABLE_AT_SELECTION")
        member_hashes = {item["revision_id"]: item["content_hash"] for item in cut.members}
        statement = statement.where(FxRateSourceRevision.revision_id.in_(member_hashes))
    else:
        child = aliased(FxRateSourceRevision)
        statement = statement.where(
            ~exists(
                select(child.revision_id).where(
                    child.predecessor_revision_id == FxRateSourceRevision.revision_id,
                    *_visible(child, selection),
                )
            )
        )
    rows = (await session.scalars(statement.order_by(FxRateSourceRevision.rate_date))).all()
    if len({row.rate_date for row in rows}) != len(rows):
        raise FxSourceSelectionRejected("FX_SOURCE_PAIR_DATE_AMBIGUOUS")
    if member_hashes is not None and any(
        member_hashes[row.revision_id] != row.content_hash for row in rows
    ):
        raise FxSourceSelectionRejected("FX_SOURCE_CUT_CONTENT_MISMATCH")
    return [
        FxRateEvidence(
            from_currency=row.from_currency,
            to_currency=row.to_currency,
            rate_date=row.rate_date,
            rate=row.rate,
            created_at=row.accepted_at,
            updated_at=None,
            source=FxRateSourceEvidence(
                scope=selection.scope,
                revision_id=row.revision_id,
                content_hash=row.content_hash,
                source_observed_at=row.source_observed_at,
                accepted_at=row.accepted_at,
                fixing_kind=row.fixing_kind,
                calendar_version=row.calendar_version,
                cut_id=selection.cut_id or row.admitted_cut_id,
            ),
        )
        for row in rows
    ]
