"""Authenticate, verify typed producer facts, then create one atomic terminal receipt."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from portfolio_common.domain.portfolio_flow_source_observations import (
    FlowEventObservation,
    FlowSourceCut,
)
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationConflict,
    ObservationFamily,
    PortfolioSourceObservation,
)
from portfolio_common.domain.tenant import TenantContext
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerObservationAuthority,
    ProducerSubmissionGrant,
)
from portfolio_common.portfolio_source_observation_verification import (
    ObservationVerificationAuthority,
)

from ..application.reference_data_ingestion_registry import REFERENCE_DATA_INGESTION_REGISTRY
from ..DTOs.ingestion_job_dto import IngestionJobResponse
from ..DTOs.portfolio_source_observation_dto import (
    CashAvailabilityObservationIngestionRequest,
    FlowEventObservationIngestionRequest,
    FlowSourceCutIngestionRequest,
    FundingInvestmentObservationIngestionRequest,
)
from ..infrastructure.portfolio_source_observation_unit_of_work import (
    PortfolioFlowSourceObservationStager,
    PortfolioSourceObservationStager,
)
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..ports.ingestion_idempotency_replay import IngestionIdempotencyReplayReader
from ..request_metadata import create_ingestion_job_id, get_request_lineage
from .ingestion_job_service import IngestionJobService


@dataclass(frozen=True, slots=True)
class ObservationSubmission:
    tenant_context: TenantContext
    request: (
        CashAvailabilityObservationIngestionRequest
        | FundingInvestmentObservationIngestionRequest
        | FlowEventObservationIngestionRequest
        | FlowSourceCutIngestionRequest
    )
    idempotency_key: str
    correlation_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    received_at: datetime | None = None


class PortfolioSourceObservationCommands:
    def __init__(
        self,
        authority: ProducerObservationAuthority,
        service_factory: Callable[[PortfolioSourceObservationStager], IngestionJobService],
        idempotency_replay_reader: IngestionIdempotencyReplayReader,
        verification_authority: ObservationVerificationAuthority | None = None,
    ):
        self.authority = authority
        self.service_factory = service_factory
        self.idempotency_replay_reader = idempotency_replay_reader
        self.verification_authority = verification_authority or ObservationVerificationAuthority()

    @staticmethod
    def _grant(fact) -> ProducerSubmissionGrant:
        if isinstance(fact, FlowSourceCut):
            return ProducerSubmissionGrant(
                fact.tenant_id,
                fact.portfolio_id,
                fact.source_system,
                ObservationFamily.FLOW_EVENT,
            )
        return ProducerSubmissionGrant(
            fact.envelope.tenant_id,
            fact.envelope.portfolio_id,
            fact.envelope.producer_id,
            fact.family,
        )

    async def submit(self, submission: ObservationSubmission) -> IngestionJobResponse:
        context = submission.tenant_context
        if not context.identity_verified or not submission.idempotency_key.strip():
            raise ObservationConflict("SOURCE_OBSERVATION_PRODUCER_NOT_ADMITTED")
        cut_request = isinstance(submission.request, FlowSourceCutIngestionRequest)
        flow_request = isinstance(submission.request, FlowEventObservationIngestionRequest)
        facts: tuple[PortfolioSourceObservation | FlowEventObservation | FlowSourceCut, ...]
        if isinstance(submission.request, FlowSourceCutIngestionRequest):
            facts = tuple(r.to_cut(context.tenant_id_text) for r in submission.request.cuts)
        else:
            facts = tuple(
                r.to_observation(context.tenant_id_text) for r in submission.request.observations
            )
        admissions = tuple(self.authority.admit(context, self._grant(f)) for f in facts)
        key = (
            "portfolio_flow_source_cut"
            if cut_request
            else "portfolio_flow_event_observation"
            if flow_request
            else "portfolio_cash_availability_observation"
            if isinstance(submission.request, CashAvailabilityObservationIngestionRequest)
            else "portfolio_funding_investment_observation"
        )
        command = REFERENCE_DATA_INGESTION_REGISTRY.require(key)
        attestations = (
            ()
            if cut_request
            else tuple(r.verification_receipt for r in submission.request.observations)
        )
        for fact, attestation in zip(
            facts, attestations if not cut_request else (None,), strict=True
        ):
            if attestation is not None:
                if isinstance(fact, (FlowEventObservation, FlowSourceCut)):
                    raise ObservationConflict("FLOW_SOURCE_FACT_VERIFICATION_UNSUPPORTED")
                self.verification_authority.verify_fact(
                    fact,
                    attestation,
                    consumer_id=attestation.claims.subject.consumer_id,
                    as_of_date=attestation.claims.subject.as_of_date,
                    now=datetime.now(UTC),
                )
        if cut_request or flow_request:
            if submission.received_at is None or submission.received_at.utcoffset() is None:
                raise ValueError("trusted admitted flow ingress timestamp required")
            stager = PortfolioFlowSourceObservationStager(
                facts,
                admissions,
                submission.received_at,
                cut_request,
            )
        else:
            legacy_facts = tuple(
                f
                for f in facts
                if isinstance(
                    f,
                    (CashAvailabilityObservation, FundingInvestmentObservation),
                )
            )
            if len(legacy_facts) != len(facts):
                raise TypeError("legacy observation command requires its declared family")
            stager = PortfolioSourceObservationStager(
                legacy_facts, admissions, attestations, self.verification_authority
            )
        service = self.service_factory(stager)
        request_payload = command.request_payload(submission.request)
        replay = await self.idempotency_replay_reader.find_matching_job(
            tenant_id=context.tenant_id_text,
            endpoint=command.endpoint,
            idempotency_key=submission.idempotency_key,
            request_payload=request_payload,
        )
        if replay is not None:
            job = await service.get_job(replay.job_id, tenant_id=context.tenant_id_text)
            if (
                replay.status != "completed"
                or job is None
                or job.status != "completed"
                or job.completed_at is None
            ):
                raise ObservationConflict("SOURCE_OBSERVATION_RECEIPT_NOT_COMPLETED")
            return job
        try:
            await service.assert_ingestion_writable()
        except PermissionError as exc:
            raise ObservationConflict("INGESTION_MODE_BLOCKS_WRITES") from exc
        try:
            enforce_ingestion_write_rate_limit(endpoint=command.endpoint, record_count=len(facts))
        except PermissionError as exc:
            raise ObservationConflict("INGESTION_RATE_LIMIT_EXCEEDED") from exc
        correlation_id, request_id, trace_id = get_request_lineage()
        result = await service.create_or_get_job(
            job_id=create_ingestion_job_id(),
            tenant_context=context,
            endpoint=command.endpoint,
            entity_type=command.entity_type,
            accepted_count=len(facts),
            idempotency_key=submission.idempotency_key,
            correlation_id=submission.correlation_id
            if submission.correlation_id is not None
            else correlation_id or "",
            request_id=submission.request_id
            if submission.request_id is not None
            else request_id or "",
            trace_id=submission.trace_id if submission.trace_id is not None else trace_id or "",
            request_payload=request_payload,
        )
        if result.job.status != "completed" or result.job.completed_at is None:
            raise ObservationConflict("SOURCE_OBSERVATION_RECEIPT_NOT_COMPLETED")
        return result.job
