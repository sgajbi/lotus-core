"""Append/CAS inside the supplied receipt transaction; never commit or dispatch."""

from dataclasses import asdict
from datetime import datetime

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationConflict,
    ObservationEnvelope,
    PortfolioSourceObservation,
    require_successor,
)
from portfolio_common.portfolio_source_observation_models import (
    SOURCE_IDENTITY_COLUMNS,
    CashAvailabilityObservationHead,
    CashAvailabilityObservationRow,
    FundingInvestmentObservationHead,
    FundingInvestmentObservationRow,
    observation_from_row,
)
from portfolio_common.portfolio_source_observation_qualification import UnqualifiedProducerAdmission
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


def _family_models(fact: PortfolioSourceObservation):
    if isinstance(fact, CashAvailabilityObservation):
        return CashAvailabilityObservationRow, CashAvailabilityObservationHead
    return FundingInvestmentObservationRow, FundingInvestmentObservationHead


def _scope_predicates(model, envelope: ObservationEnvelope):
    return [getattr(model, name) == getattr(envelope, name) for name in SOURCE_IDENTITY_COLUMNS]


class PortfolioSourceObservationWriter:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def append_cash_availability_observations(
        self,
        facts: tuple[PortfolioSourceObservation, ...],
        admissions: tuple[UnqualifiedProducerAdmission, ...],
        *,
        receipt_job_id: str,
        received_at: datetime,
    ) -> tuple[str, ...]:
        if any(not isinstance(fact, CashAvailabilityObservation) for fact in facts):
            raise TypeError("cash command requires cash observation facts")
        return await self.append(
            facts, admissions, receipt_job_id=receipt_job_id, received_at=received_at
        )

    async def append_funding_investment_observations(
        self,
        facts: tuple[PortfolioSourceObservation, ...],
        admissions: tuple[UnqualifiedProducerAdmission, ...],
        *,
        receipt_job_id: str,
        received_at: datetime,
    ) -> tuple[str, ...]:
        if any(not isinstance(fact, FundingInvestmentObservation) for fact in facts):
            raise TypeError("funding command requires funding/investment observation facts")
        return await self.append(
            facts, admissions, receipt_job_id=receipt_job_id, received_at=received_at
        )

    async def append(
        self,
        facts: tuple[PortfolioSourceObservation, ...],
        admissions: tuple[UnqualifiedProducerAdmission, ...],
        *,
        receipt_job_id: str,
        received_at: datetime,
    ) -> tuple[str, ...]:
        if not self.session.in_transaction():
            raise RuntimeError(
                "source observations require the supplied active receipt transaction"
            )
        if not facts or len(facts) != len(admissions):
            raise ValueError("each observation requires explicit server admission")
        pairs = tuple(zip(facts, admissions, strict=True))
        identities = [(fact.family, fact.envelope.source_key) for fact in facts]
        if len(set(identities)) != len(identities):
            raise ObservationConflict("SOURCE_OBSERVATION_DUPLICATE_SOURCE")
        for fact, admission in pairs:
            self._require_admission(fact, admission)
        # Serialize source revisions separately from competing authority scopes.
        # Different coverage scopes/currencies progress independently; no FX join.
        locks = sorted(
            {
                canonical_content_hash(
                    {
                        "tenant": f.envelope.tenant_id,
                        "portfolio": f.envelope.portfolio_id,
                        "producer": f.envelope.producer_id,
                        "family": f.family.value,
                        "coverage_scope": f.envelope.coverage_scope,
                        "currency": f.currency
                        if isinstance(f, CashAvailabilityObservation)
                        else None,
                    }
                )
                for f in facts
            }
        )
        locks = sorted(
            set(locks)
            | {
                canonical_content_hash(
                    {"source_key": f.envelope.source_key, "family": f.family.value}
                )
                for f in facts
            }
        )
        for lock in locks:
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"), {"scope": lock}
            )
        accepted = []
        for fact, admission in pairs:
            accepted.append(
                await self._append_one(
                    fact, admission, receipt_job_id=receipt_job_id, received_at=received_at
                )
            )
        await self.session.flush()
        return tuple(accepted)

    @staticmethod
    def _require_admission(fact, admission):
        grant = admission.grant
        envelope = fact.envelope
        if (
            grant.tenant_id != envelope.tenant_id
            or grant.portfolio_id != envelope.portfolio_id
            or grant.producer_id != envelope.producer_id
            or grant.family != fact.family
            or admission.qualification != "unqualified"
        ):
            raise ObservationConflict("SOURCE_OBSERVATION_PRODUCER_NOT_ADMITTED")

    async def _append_one(self, fact, admission, *, receipt_job_id, received_at):
        row_model, head_model = _family_models(fact)
        envelope = fact.envelope
        existing = await self.session.scalar(
            select(row_model).where(
                *_scope_predicates(row_model, envelope),
                row_model.source_revision == envelope.source_revision,
            )
        )
        if existing is not None:
            stored = observation_from_row(existing)
            if stored.content_hash != fact.content_hash:
                raise ObservationConflict("SOURCE_OBSERVATION_DIVERGENT_REPLAY")
            # Replaying an original after correction never rewinds the head.
            return existing.observation_id
        head = await self.session.scalar(
            select(head_model).where(*_scope_predicates(head_model, envelope)).with_for_update()
        )
        if head is None:
            if envelope.source_revision != 1:
                raise ObservationConflict("SOURCE_OBSERVATION_STALE_HEAD")
        else:
            original = await self.session.scalar(
                select(row_model).where(
                    *_scope_predicates(row_model, envelope),
                    row_model.observation_id == head.observation_id,
                )
            )
            if original is None:
                raise ObservationConflict("SOURCE_OBSERVATION_STALE_HEAD")
            require_successor(observation_from_row(original), fact, original_id=head.observation_id)
        await self._refuse_competing_interval(row_model, head_model, fact)
        values = asdict(envelope)
        values["coverage"] = envelope.coverage.value
        if isinstance(fact, CashAvailabilityObservation):
            values.update(
                currency=fact.currency,
                settled_amount=fact.settled,
                encumbered_amount=fact.encumbered,
                available_amount=fact.available,
            )
        else:
            values.update(funded=fact.funded, invested=fact.invested)
        row = row_model(
            **values,
            observation_id=fact.content_hash,
            content_hash=fact.content_hash,
            receipt_job_id=receipt_job_id,
            received_at=received_at,
            admission_policy_version=admission.policy_version,
            qualification=admission.qualification,
        )
        self.session.add(row)
        # The immutable fact must exist before its scoped head FK is changed.
        await self.session.flush()
        if head is None:
            self.session.add(
                head_model(
                    **{name: getattr(envelope, name) for name in SOURCE_IDENTITY_COLUMNS},
                    observation_id=fact.content_hash,
                    content_hash=fact.content_hash,
                )
            )
        else:
            head.observation_id = fact.content_hash
            head.content_hash = fact.content_hash
        await self.session.flush()
        return fact.content_hash

    async def _refuse_competing_interval(self, row_model, head_model, fact):
        envelope = fact.envelope
        authority_scope = [row_model.coverage_scope == envelope.coverage_scope]
        if envelope.effective_to is not None:
            authority_scope.append(row_model.effective_from < envelope.effective_to)
        if isinstance(fact, CashAvailabilityObservation):
            authority_scope.append(row_model.currency == fact.currency)
        competing = await self.session.scalar(
            select(row_model.observation_id)
            .join(
                head_model,
                (head_model.observation_id == row_model.observation_id)
                & (head_model.content_hash == row_model.content_hash),
            )
            .where(
                row_model.tenant_id == envelope.tenant_id,
                row_model.portfolio_id == envelope.portfolio_id,
                row_model.producer_id == envelope.producer_id,
                *authority_scope,
                row_model.source_record_id != envelope.source_record_id,
                (row_model.effective_to.is_(None))
                | (row_model.effective_to > envelope.effective_from),
            )
            .limit(1)
        )
        if competing is not None:
            raise ObservationConflict("SOURCE_OBSERVATION_AMBIGUOUS_OVERLAP")
