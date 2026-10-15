"""Complete source-field projection; independent whole-assembly approval stays downstream."""

from dataclasses import asdict
from datetime import UTC, datetime

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_flow_source_observations import require_flow_cut_events
from portfolio_common.page_tokens import PageTokenCodec
from portfolio_common.source_data_product_metadata import (
    SourceDataDegradationSummary,
    source_data_product_runtime_metadata,
)

from ..contracts.portfolio_flow_source_observations import (
    FlowEventEvidence,
    FlowEventRevisionResponse,
    FlowPage,
    PortfolioFlowObservationsResponse,
)
from ..ports.portfolio_flow_source_observations import PortfolioFlowObservationReader

FLOW_PAGE_ROUTE = "PortfolioFinancialFlowObservations/v1"


def project_event(record) -> FlowEventEvidence:
    fact, envelope = record.fact, record.fact.envelope
    if record.received_at.utcoffset() is None or not record.receipt_job_id:
        raise ValueError("actual flow receipt unavailable")
    return FlowEventEvidence(
        **{k: v for k, v in asdict(fact).items() if k not in {"envelope", "amount"}},
        amount=str(fact.amount),
        source_record_id=envelope.source_record_id,
        received_at=record.received_at,
        receipt_job_id=record.receipt_job_id,
        observation_id=fact.content_hash,
        content_hash=fact.content_hash,
        source_system=envelope.producer_id,
        flow_source_record_revision=envelope.source_revision,
        source_cut_id=envelope.source_cut_id,
        definition_version=envelope.definition_version,
        predecessor_id=envelope.predecessor_id,
        expected_head_hash=envelope.expected_head_hash,
        coverage=envelope.coverage.value,
    )


class PortfolioFlowObservationsService:
    def __init__(self, reader: PortfolioFlowObservationReader, page_tokens: PageTokenCodec):
        self.reader = reader
        self.page_tokens = page_tokens

    async def event(self, **selection) -> FlowEventRevisionResponse:
        record = await self.reader.read_event(**selection)
        if record is None:
            raise LookupError("flow event revision unavailable")
        envelope = record.fact.envelope
        if (
            envelope.tenant_id,
            envelope.portfolio_id,
            envelope.producer_id,
            envelope.source_record_id,
            envelope.source_revision,
        ) != (
            selection["tenant_id"],
            selection["portfolio_id"],
            selection["source_system"],
            selection["source_record_id"],
            selection["flow_source_record_revision"],
        ):
            raise ValueError("flow event revision scope mismatch")
        evidence = project_event(record)
        metadata = source_data_product_runtime_metadata(
            as_of_date=record.fact.business_date,
            generated_at=datetime.now(UTC),
            tenant_id=selection["tenant_id"],
            data_quality_status="UNAVAILABLE",
            source_evidence_current=False,
            freshness_status="UNAVAILABLE",
            source_cut_id=record.fact.envelope.source_cut_id,
            content_hash=record.fact.content_hash,
            source_refs=[
                "lotus-core://source/PortfolioFinancialFlowObservations/" + record.fact.content_hash
            ],
            lineage={"source_owner": "lotus-core", "qualification": "unqualified"},
        )
        return FlowEventRevisionResponse(
            **{**metadata, **evidence.model_dump()},
            degradation=SourceDataDegradationSummary(
                status="UNAVAILABLE",
                reason_codes=["SOURCE_PRODUCER_UNQUALIFIED", "COMPLETE_WINDOW_NOT_ESTABLISHED"],
            ),
        )

    async def query(self, *, tenant_id, portfolio_id, request) -> PortfolioFlowObservationsResponse:
        record = await self.reader.read_cut(
            tenant_id=tenant_id,
            portfolio_id=portfolio_id,
            request=request,
        )
        if record is None:
            raise LookupError("exact flow source cut unavailable")
        cut = record.cut
        if (
            cut.tenant_id,
            cut.portfolio_id,
            cut.source_system,
            cut.source_cut_id,
            cut.cut_revision,
            cut.content_hash,
            cut.currency,
            cut.coverage_from,
            cut.coverage_to,
        ) != (
            tenant_id,
            portfolio_id,
            request.source_system,
            request.source_cut_id,
            request.cut_revision,
            request.manifest_hash,
            request.currency,
            request.window.from_date,
            request.window.to_date,
        ):
            raise ValueError("flow cut scope, currency or coverage window mismatch")
        available = require_flow_cut_events(
            cut, tuple(e.fact for e in record.events), tuple(e.fact for e in record.dependencies)
        )
        events = sorted((project_event(e) for e in record.events), key=lambda e: e.source_record_id)
        dependencies = sorted(
            (project_event(e) for e in record.dependencies),
            key=lambda e: (e.source_record_id, e.flow_source_record_revision, e.observation_id),
        )
        dependency_payload = [e.model_dump(mode="json") for e in dependencies]
        dependency_digest = canonical_content_hash({"reversal_dependencies": dependency_payload})
        digest = canonical_content_hash(
            {
                "events": [e.model_dump(mode="json") for e in events],
                "reversal_dependencies": dependency_payload,
            }
        )
        scope = canonical_content_hash(
            {
                "tenant": tenant_id,
                "portfolio": portfolio_id,
                "selection": request.model_dump(mode="json", exclude={"page"}),
                "page_size": request.page.page_size,
                "ordered_set_hash": digest,
            }
        )
        offset = self._offset(
            request.page.page_token, tenant_id, scope, len(events), request.page.page_size
        )
        end = min(offset + request.page.page_size, len(events))
        token = (
            self.page_tokens.encode(
                {"scope": scope, "offset": end}, route=FLOW_PAGE_ROUTE, tenant_id=tenant_id
            )
            if end < len(events)
            else None
        )
        reasons = ["SOURCE_PRODUCER_UNQUALIFIED", "WHOLE_ASSEMBLY_VERIFICATION_NOT_ESTABLISHED"]
        if not available:
            reasons.append("FLOW_SOURCE_FIELDS_UNAVAILABLE")
        metadata = source_data_product_runtime_metadata(
            as_of_date=cut.coverage_to,
            generated_at=datetime.now(UTC),
            tenant_id=tenant_id,
            data_quality_status="UNAVAILABLE",
            source_evidence_current=False,
            freshness_status="UNAVAILABLE",
            source_cut_id=cut.source_cut_id,
            content_hash=cut.content_hash,
            source_refs=[
                f"lotus-core://source/PortfolioFinancialFlowObservations/{portfolio_id}/{cut.content_hash}"
            ],
            lineage={"source_owner": "lotus-core", "qualification": "unqualified"},
        )
        return PortfolioFlowObservationsResponse(
            **{**metadata, "source_cut_id": cut.source_cut_id},
            portfolio_id=portfolio_id,
            source_system=cut.source_system,
            cut_revision=cut.cut_revision,
            manifest_hash=cut.content_hash,
            definition_version=cut.definition_version,
            currency=cut.currency,
            window=request.window,
            coverage=cut.coverage.value,
            source_fields_available=available,
            reason_codes=reasons,
            receipt_job_id=record.receipt_job_id,
            received_at=record.received_at,
            predecessor_cut_hash=cut.predecessor_cut_hash,
            expected_head_hash=cut.expected_head_hash,
            pagination=FlowPage(
                total_count=len(events),
                returned_count=end - offset,
                offset=offset,
                next_page_token=token,
                ordered_set_hash=digest,
                dependency_count=len(dependencies),
                dependency_set_hash=dependency_digest,
            ),
            events=events[offset:end],
            reversal_dependencies=dependencies,
            degradation=SourceDataDegradationSummary(status="UNAVAILABLE", reason_codes=reasons),
        )

    def _offset(self, token, tenant_id, scope, total, page_size):
        if token is None:
            return 0
        payload = self.page_tokens.decode(token, route=FLOW_PAGE_ROUTE, tenant_id=tenant_id)
        offset = payload.get("offset")
        if (
            set(payload) != {"scope", "offset"}
            or payload.get("scope") != scope
            or type(offset) is not int
            or not 0 < offset < total
            or offset % page_size != 0
        ):
            raise ValueError("flow page cursor scope or position mismatch")
        return offset
