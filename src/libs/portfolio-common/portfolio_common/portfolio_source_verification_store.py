"""Owning transaction receipt linkage and read-time re-verification, without commits."""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .domain.portfolio_source_observations import CashAvailabilityObservation, ObservationConflict
from .domain.portfolio_source_verification import SignedObservationVerificationReceipt
from .portfolio_source_observation_models import (
    SOURCE_IDENTITY_COLUMNS,
    CashAvailabilityObservationRow,
    FundingInvestmentObservationRow,
    observation_from_row,
)
from .portfolio_source_verification_models import PortfolioSourceVerificationRow


class PortfolioSourceVerificationStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def append(self, fact, receipt, *, authority, consumer_id, as_of_date, now):
        if not self.session.in_transaction():
            raise RuntimeError("verification requires supplied active fact transaction")
        verified = authority.verify_fact(
            fact, receipt, consumer_id=consumer_id, as_of_date=as_of_date, now=now
        )
        model = (
            CashAvailabilityObservationRow
            if isinstance(fact, CashAvailabilityObservation)
            else FundingInvestmentObservationRow
        )
        row = await self.session.scalar(
            select(model)
            .where(
                *(
                    getattr(model, name) == getattr(fact.envelope, name)
                    for name in SOURCE_IDENTITY_COLUMNS
                ),
                model.observation_id == fact.content_hash,
            )
            .with_for_update()
        )
        if row is None or observation_from_row(row) != fact:
            raise ObservationConflict("SOURCE_VERIFICATION_FACT_CUSTODY_MISMATCH")
        digest = verified.attestation_sha256
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:digest, 0))"), {"digest": digest}
        )
        existing = await self.session.get(PortfolioSourceVerificationRow, digest)
        if existing is None:
            self.session.add(
                PortfolioSourceVerificationRow(
                    attestation_sha256=digest,
                    **{name: getattr(fact.envelope, name) for name in SOURCE_IDENTITY_COLUMNS},
                    content_hash=fact.content_hash,
                    cash_observation_id=fact.content_hash
                    if isinstance(fact, CashAvailabilityObservation)
                    else None,
                    funding_observation_id=None
                    if isinstance(fact, CashAvailabilityObservation)
                    else fact.content_hash,
                    consumer_id=consumer_id,
                    receipt=verified.receipt.model_dump(mode="json"),
                    received_at=now,
                )
            )
            await self.session.flush()
        elif existing.receipt != verified.receipt.model_dump(mode="json"):
            raise ObservationConflict("SOURCE_VERIFICATION_DIVERGENT_RECEIPT")
        return digest

    async def receipts(self, fact, *, consumer_id):
        result = await self.session.scalars(
            select(PortfolioSourceVerificationRow)
            .where(
                *(
                    getattr(PortfolioSourceVerificationRow, name) == getattr(fact.envelope, name)
                    for name in SOURCE_IDENTITY_COLUMNS
                ),
                PortfolioSourceVerificationRow.content_hash == fact.content_hash,
                PortfolioSourceVerificationRow.consumer_id == consumer_id,
            )
            .order_by(
                PortfolioSourceVerificationRow.received_at.desc(),
                PortfolioSourceVerificationRow.attestation_sha256,
            )
        )
        return tuple(
            SignedObservationVerificationReceipt.model_validate(row.receipt) for row in result.all()
        )
