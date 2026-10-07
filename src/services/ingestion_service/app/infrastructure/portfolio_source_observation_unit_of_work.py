"""Capability-specific creation effect in the native ingestion receipt transaction."""

from dataclasses import dataclass

from portfolio_common.database_models import IngestionJob
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    PortfolioSourceObservation,
)
from portfolio_common.portfolio_source_observation_qualification import UnqualifiedProducerAdmission
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.reference_data_ingestion_registry import REFERENCE_DATA_INGESTION_REGISTRY
from ..services.ingestion_job_lifecycle import complete_synchronous_observation_receipt
from ..services.portfolio_source_observation_writer import PortfolioSourceObservationWriter


@dataclass(frozen=True, slots=True)
class PortfolioSourceObservationStager:
    facts: tuple[PortfolioSourceObservation, ...]
    admissions: tuple[UnqualifiedProducerAdmission, ...]

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
        await complete_synchronous_observation_receipt(
            session, receipt, tenant_id=receipt.tenant_id, job_id=receipt.job_id
        )
