"""Capability-specific creation effect in the native ingestion receipt transaction."""

from dataclasses import dataclass
from datetime import UTC, datetime

from portfolio_common.database_models import IngestionJob
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    PortfolioSourceObservation,
)
from portfolio_common.domain.portfolio_source_verification import (
    SignedObservationVerificationReceipt,
)
from portfolio_common.portfolio_source_observation_qualification import UnqualifiedProducerAdmission
from portfolio_common.portfolio_source_observation_verification import (
    ObservationVerificationAuthority,
)
from portfolio_common.portfolio_source_verification_store import PortfolioSourceVerificationStore
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.reference_data_ingestion_registry import REFERENCE_DATA_INGESTION_REGISTRY
from ..services.ingestion_job_lifecycle import complete_synchronous_observation_receipt
from ..services.portfolio_source_observation_writer import PortfolioSourceObservationWriter


@dataclass(frozen=True, slots=True)
class PortfolioSourceObservationStager:
    facts: tuple[PortfolioSourceObservation, ...]
    admissions: tuple[UnqualifiedProducerAdmission, ...]
    verifications: tuple[SignedObservationVerificationReceipt | None, ...] = ()
    verification_authority: ObservationVerificationAuthority | None = None

    async def stage(self, session: AsyncSession, receipt: IngestionJob) -> None:
        if not self.facts:
            raise ValueError("observation creation effect requires facts")
        cash = isinstance(self.facts[0], CashAvailabilityObservation)
        command_key = (
            "portfolio_cash_availability_observation"
            if cash
            else "portfolio_funding_investment_observation"
        )
        command = REFERENCE_DATA_INGESTION_REGISTRY.require(command_key)
        if (
            receipt.endpoint != command.endpoint
            or receipt.entity_type != command.entity_type
            or receipt.accepted_count != len(self.facts)
            or any(
                f.envelope.tenant_id != receipt.tenant_id or f.family != self.facts[0].family
                for f in self.facts
            )
        ):
            raise ValueError("observation creation effect does not match its receipt")
        writer = PortfolioSourceObservationWriter(session)
        append = getattr(writer, command.persist_method_name)
        await append(
            self.facts,
            self.admissions,
            receipt_job_id=receipt.job_id,
            received_at=receipt.submitted_at,
        )
        if self.verifications:
            if len(self.verifications) != len(self.facts) or self.verification_authority is None:
                raise ValueError("verification must match the atomic fact batch")
            store = PortfolioSourceVerificationStore(session)
            now = datetime.now(UTC)
            for fact, attestation in zip(self.facts, self.verifications, strict=True):
                if attestation is not None:
                    await store.append(
                        fact,
                        attestation,
                        authority=self.verification_authority,
                        consumer_id=attestation.claims.subject.consumer_id,
                        as_of_date=attestation.claims.subject.as_of_date,
                        now=now,
                    )
        await complete_synchronous_observation_receipt(
            session, receipt, tenant_id=receipt.tenant_id, job_id=receipt.job_id
        )
