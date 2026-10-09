"""Retain one complete FX cut inside the existing consumer-owned unit of work."""

from dataclasses import dataclass
from datetime import datetime
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    canonical_content_hash,
    require_sha256_digest,
)
from portfolio_common.domain.market_data.fx_source import (
    FxSourceCut,
    FxSourceRevision,
    FxSourceScope,
)
from portfolio_common.fx_source_admission import FxSourceAdmission
from portfolio_common.fx_source_models import FxRateSourceCut, FxRateSourceRevision
from sqlalchemy import exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased


class FxSourceConflict(ValueError):
    """Bounded source conflict; caller facts never overwrite retained authority."""


@dataclass(frozen=True)
class RetainedFxCutResult:
    row: FxRateSourceCut
    replayed: bool


def _scope_predicates(model, scope: FxSourceScope) -> tuple:
    return (
        model.tenant_id == scope.tenant_id,
        model.provider_id == scope.provider_id,
        model.source_id == scope.source_id,
    )


class FxSourceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_cut(self, cut: FxSourceCut) -> FxRateSourceCut | None:
        return cast(
            FxRateSourceCut | None,
            await self.db.scalar(
                select(FxRateSourceCut).where(
                    FxRateSourceCut.cut_id == cut.cut_id,
                    *_scope_predicates(FxRateSourceCut, cut.scope),
                )
            ),
        )

    async def retain_admitted_cut(
        self, admission: FxSourceAdmission, *, attestation_sha256: str
    ) -> RetainedFxCutResult:
        """No commit/savepoint: cut, revisions, inbox and outbox share the caller's UOW.

        Admission must first be authenticated at the consumer boundary. Advisory
        transaction locks serialize missing roots as well as existing predecessors;
        FK/unique constraints independently prevent a fork or cross-scope chain.
        """
        if not self.db.in_transaction() or self.db.in_nested_transaction():
            raise FxSourceConflict("FX_SOURCE_OWNING_TRANSACTION_REQUIRED")
        require_sha256_digest(attestation_sha256, "attestation_sha256")
        cut = admission.cut
        await self._lock_cut_and_chains(cut)
        existing_cut = await self.find_cut(cut)
        if existing_cut is not None:
            if existing_cut.content_hash != cut.content_hash:
                raise FxSourceConflict("FX_SOURCE_CUT_VERSION_CONFLICT")
            return RetainedFxCutResult(existing_cut, True)
        new_members = []
        for member in cut.revisions:
            existing = await self.db.get(FxRateSourceRevision, member.revision_id)
            if existing is not None:
                if existing.content_hash != member.content_hash:
                    raise FxSourceConflict("FX_SOURCE_REVISION_VERSION_CONFLICT")
            else:
                await self._require_predecessor(member)
                new_members.append(member)
        accepted_at: datetime = await self.db.scalar(select(func.clock_timestamp()))
        row = FxRateSourceCut(
            cut_id=cut.cut_id,
            **cut.scope.content(),
            source_cut_reference=cut.source_cut_reference,
            source_cut_revision=cut.source_cut_revision,
            source_observed_cutoff=cut.source_observed_cutoff,
            accepted_at=accepted_at,
            member_count=cut.declared_member_count,
            members=[
                {"revision_id": member.revision_id, "content_hash": member.content_hash}
                for member in sorted(cut.revisions, key=lambda item: item.revision_id)
            ],
            membership_hash=cut.declared_membership_hash,
            content_hash=cut.content_hash,
            admission_receipt={
                "attestation_sha256": attestation_sha256,
                "principal": admission.principal,
                "enrollment_version": admission.enrollment_version,
                "calendar_version": admission.calendar_version,
                "ingress_accepted_at": admission.accepted_at.isoformat(),
            },
        )
        self.db.add(row)
        await self.db.flush()
        for member in new_members:
            self.db.add(
                FxRateSourceRevision(
                    revision_id=member.revision_id,
                    **member.scope.content(),
                    source_record_id=member.source_record_id,
                    source_revision=member.source_revision,
                    from_currency=member.from_currency,
                    to_currency=member.to_currency,
                    rate_date=member.rate_date,
                    rate=member.rate,
                    source_observed_at=member.source_observed_at,
                    accepted_at=accepted_at,
                    fixing_kind=member.fixing_kind,
                    calendar_version=member.calendar_version,
                    predecessor_revision_id=member.predecessor_revision_id,
                    content_hash=member.content_hash,
                    admitted_cut_id=cut.cut_id,
                )
            )
        await self.db.flush()
        return RetainedFxCutResult(row, False)

    async def _lock_cut_and_chains(self, cut: FxSourceCut) -> None:
        identities = {canonical_content_hash({"cut_id": cut.cut_id})}
        identities.update(
            canonical_content_hash({**member.scope.content(), "record": member.source_record_id})
            for member in cut.revisions
        )
        for digest in sorted(identities):
            key = int.from_bytes(bytes.fromhex(digest[:16]), "big", signed=True)
            await self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    async def _require_predecessor(self, member: FxSourceRevision) -> None:
        child = aliased(FxRateSourceRevision)
        heads = (
            await self.db.scalars(
                select(FxRateSourceRevision)
                .where(
                    *_scope_predicates(FxRateSourceRevision, member.scope),
                    FxRateSourceRevision.source_record_id == member.source_record_id,
                    ~exists(
                        select(child.revision_id).where(
                            child.predecessor_revision_id == FxRateSourceRevision.revision_id
                        )
                    ),
                )
                .with_for_update()
            )
        ).all()
        if len(heads) > 1:
            raise FxSourceConflict("FX_SOURCE_CHAIN_CONFLICT")
        expected = heads[0].revision_id if heads else None
        if member.predecessor_revision_id != expected:
            raise FxSourceConflict("FX_SOURCE_STALE_PREDECESSOR")
        if heads and (
            heads[0].from_currency != member.from_currency
            or heads[0].to_currency != member.to_currency
            or heads[0].rate_date != member.rate_date
        ):
            raise FxSourceConflict("FX_SOURCE_CORRECTION_CHAIN_MISMATCH")
