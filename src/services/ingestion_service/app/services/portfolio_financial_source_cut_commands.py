"""Exact registry admission and native atomic custody receipts, without producer proof inflation."""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.domain.tenant import TenantContext
from portfolio_common.portfolio_financial_source_cut_admission import (
    RegistrySourceGrant,
    require_chunk_budget,
    require_registry_source_grant,
)

from ..application.reference_data_ingestion_registry import REFERENCE_DATA_INGESTION_REGISTRY
from ..DTOs.portfolio_financial_source_cut_dto import (
    FinancialChunkInput,
    FinancialSealInput,
    RegistryChunkInput,
    RegistrySealInput,
)
from ..infrastructure.portfolio_financial_source_cut_stager import (
    PortfolioFinancialSourceCutStager,
    command_kind,
)
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..request_metadata import create_ingestion_job_id, get_request_lineage


@dataclass(frozen=True, slots=True)
class NeutralSourceSubmission:
    tenant_context: TenantContext
    request: RegistryChunkInput | RegistrySealInput | FinancialChunkInput | FinancialSealInput
    idempotency_key: str
    raw_bytes: bytes
    received_at: datetime


class PortfolioFinancialSourceCutCommands:
    def __init__(self, grants: tuple[RegistrySourceGrant, ...], service_factory, session_factory):
        self.grants = grants
        self.service_factory = service_factory
        self.sessions = session_factory

    async def submit(self, submission: NeutralSourceSubmission):
        context, request = submission.tenant_context, submission.request
        if (
            not context.identity_verified
            or context.service_identity != request.source_system
            or not submission.idempotency_key.strip()
        ):
            raise PermissionError("SOURCE_REGISTRY_PRODUCER_NOT_ADMITTED")
        product, chunk = command_kind(request)
        require_registry_source_grant(
            self.grants,
            tenant_id=context.tenant_id_text,
            source_system=request.source_system,
            registry_scope_id=request.registry_scope_id,
            product=product,
        )
        count = (
            len(request.members)
            if isinstance(request, RegistryChunkInput)
            else len(request.selections)
            if isinstance(request, FinancialChunkInput)
            else 1
        )
        require_chunk_budget(submission.raw_bytes, count)
        if submission.received_at.utcoffset() is None:
            raise ValueError("trusted aware neutral ingress time required")
        key = (
            "portfolio_historical_registry"
            if product == "PortfolioHistoricalRegistry"
            else "portfolio_financial_source_cut"
        )
        command = REFERENCE_DATA_INGESTION_REGISTRY.require(key + ("_chunk" if chunk else ""))
        stager = PortfolioFinancialSourceCutStager(
            request,
            context.tenant_id_text,
            submission.raw_bytes,
            submission.received_at,
            command.endpoint,
            command.entity_type,
        )
        service = self.service_factory(stager)
        replay = await self._original(stager, service)
        if replay is not None:
            return replay
        try:
            await service.assert_ingestion_writable()
        except PermissionError as error:
            raise ObservationConflict("INGESTION_MODE_BLOCKS_WRITES") from error
        try:
            enforce_ingestion_write_rate_limit(endpoint=command.endpoint, record_count=count)
        except PermissionError as error:
            raise ObservationConflict("INGESTION_RATE_LIMIT_EXCEEDED") from error
        correlation_id, request_id, trace_id = get_request_lineage()
        try:
            result = await service.create_or_get_job(
                job_id=create_ingestion_job_id(),
                tenant_context=context,
                endpoint=command.endpoint,
                entity_type=command.entity_type,
                accepted_count=count,
                idempotency_key=submission.idempotency_key,
                correlation_id=correlation_id or "",
                request_id=request_id or "",
                trace_id=trace_id or "",
                request_payload=command.request_payload(request)
                | {
                    "ingress_raw_sha256": hashlib.sha256(submission.raw_bytes).hexdigest(),
                },
            )
        except ObservationConflict as error:
            if str(error) not in {
                "SOURCE_CHUNK_EXISTING_RECEIPT_REQUIRED",
                "SOURCE_SEAL_EXISTING_RECEIPT_REQUIRED",
            }:
                raise
            replay = await self._original(stager, service)
            if replay is None:
                raise
            return replay
        return result.job

    async def _original(self, stager, service):
        job_id = await stager.original_receipt(self.sessions)
        if job_id is None:
            return None
        job = await service.get_job(job_id, tenant_id=stager.tenant_id)
        if job is None or job.status not in {"accepted", "completed", "failed"}:
            raise ObservationConflict("SOURCE_CUSTODY_RECEIPT_UNAVAILABLE")
        return job
