"""Acquire existing immutable native facts/receipts; never derive a balance or bank authority."""

import json
from datetime import UTC, datetime

from portfolio_common.analytics_export_source_identity import export_source_selection_digest
from portfolio_common.database_models import AnalyticsExportJob, IngestionJob, Portfolio
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import InputRole
from portfolio_common.domain.portfolio_flow_source_observations import require_flow_cut_events
from portfolio_common.domain.portfolio_source_observations import ObservationCoverage
from portfolio_common.portfolio_financial_source_cut_admission import (
    FlowSourceSelector,
    NativeSelector,
    ObservationSourceSelector,
    ValuationSelector,
)
from portfolio_common.portfolio_financial_source_cut_models import (
    NATIVE_CAPTURE_SERIALIZERS,
    native_capture_typed_root,
)
from portfolio_common.portfolio_flow_source_observation_models import (
    FlowEventObservationRow,
    FlowSourceCutRow,
    cut_from_row,
    flow_from_row,
)
from portfolio_common.portfolio_source_observation_models import (
    CashAvailabilityObservationRow,
    FundingInvestmentObservationRow,
    observation_from_row,
)
from pydantic import TypeAdapter
from sqlalchemy import and_, select

from ..ports.financial_source_captures import (
    CapturedSourcePage,
    SourceCaptureBytes,
    SourceCaptureUnavailable,
)

NATIVE_FACT_SERIALIZERS = {role: NATIVE_CAPTURE_SERIALIZERS[role.value] for role in InputRole}


def completed_source_receipt(row, job, request, *, endpoint, entity_type):
    if (
        job is None
        or job.tenant_id != request.tenant_id
        or job.job_id != row.receipt_job_id
        or job.status != "completed"
        or not isinstance(job.completed_at, datetime)
        or job.completed_at.utcoffset() is None
        or not isinstance(row.received_at, datetime)
        or row.received_at.utcoffset() is None
        or job.completed_at < row.received_at
        or job.endpoint != endpoint
        or job.entity_type != entity_type
        or job.accepted_count < 1
    ):
        raise SourceCaptureUnavailable("SOURCE_NATIVE_COMPLETED_RECEIPT_REQUIRED")
    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "endpoint": job.endpoint,
        "entity_type": job.entity_type,
        "status": "completed",
        "completed_at": job.completed_at.isoformat(),
        "accepted_count": job.accepted_count,
    }


class NativeFinancialSourceCaptureClient:
    """Read-only acquisition sessions end before the worker opens its fenced write transaction."""

    def __init__(self, session_factory):
        self.sessions = session_factory

    async def fetch(self, request):
        try:
            selector = TypeAdapter(NativeSelector).validate_json(request.selector_json)
            if canonical_content_hash(selector.model_dump(mode="json")) != request.selector_hash:
                raise SourceCaptureUnavailable("SOURCE_NATIVE_SELECTOR_HASH_MISMATCH")
            if isinstance(selector, ObservationSourceSelector):
                return await self._observation(request, selector)
            if isinstance(selector, FlowSourceSelector):
                return await self._flow(request, selector)
            if isinstance(selector, ValuationSelector):
                return await self._valuation(request, selector)
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_ADAPTER_NOT_AVAILABLE")
        except (ValueError, UnicodeError) as error:
            if isinstance(error, SourceCaptureUnavailable):
                raise
            raise SourceCaptureUnavailable("SOURCE_NATIVE_TYPED_CONTRACT_REFUSED") from error

    async def _observation(self, request, selector):
        if (
            request.role.value != selector.kind
            or request.page_index != 0
            or request.page_token is not None
            or request.product_version != "v1"
            or request.product_name != "PortfolioFinancialSourceObservations"
            or request.expected_content_hash != selector.content_hash
            or request.source_revision != str(selector.source_version)
        ):
            raise SourceCaptureUnavailable("SOURCE_NATIVE_SELECTION_MISMATCH")
        model = (
            CashAvailabilityObservationRow
            if request.role is InputRole.CASH
            else FundingInvestmentObservationRow
        )
        family = (
            "portfolio_cash_availability_observation"
            if request.role is InputRole.CASH
            else "portfolio_funding_investment_observation"
        )
        endpoint = (
            "/ingest/portfolio-cash-availability-observations"
            if request.role is InputRole.CASH
            else "/ingest/portfolio-funding-investment-observations"
        )
        async with self.sessions() as session:
            row = await session.scalar(
                select(model).where(
                    model.tenant_id == request.tenant_id,
                    model.portfolio_id == request.portfolio_id,
                    model.producer_id == selector.producer_id,
                    model.source_record_id == selector.source_record_id,
                    model.observation_id == selector.observation_id,
                    model.content_hash == selector.content_hash,
                    model.source_cut_id == selector.source_cut_id,
                    model.source_revision == selector.source_version,
                    model.receipt_job_id == request.receipt_job_id,
                )
            )
            if row is None:
                raise SourceCaptureUnavailable("SOURCE_NATIVE_PIN_UNAVAILABLE")
            fact = observation_from_row(row)
            if row.received_at.utcoffset() is None:
                raise SourceCaptureUnavailable("SOURCE_NATIVE_RECEIPT_CHRONOLOGY_UNAVAILABLE")
            if (
                fact.envelope.coverage is not ObservationCoverage.COMPLETE
                or not fact.envelope.is_effective(selector.as_of_date)
                or (request.role is InputRole.CASH and fact.currency != request.currency)
            ):
                raise SourceCaptureUnavailable("SOURCE_NATIVE_SCOPE_OR_COVERAGE_MISMATCH")
            job = await session.scalar(
                select(IngestionJob).where(
                    IngestionJob.tenant_id == request.tenant_id,
                    IngestionJob.job_id == row.receipt_job_id,
                )
            )
            receipt = completed_source_receipt(
                row, job, request, endpoint=endpoint, entity_type=family
            )
            payload = {
                "product_name": request.product_name,
                "product_version": "v1",
                "fact": TypeAdapter(type(fact)).dump_python(fact, mode="json"),
                "observation_id": row.observation_id,
                "content_hash": fact.content_hash,
                "received_at": row.received_at.isoformat(),
                "receipt": receipt,
            }
        return await self._page(request, payload, fact.content_hash, total=1)

    async def _flow(self, request, selector):
        if (
            request.role is not InputRole.FLOWS
            or request.product_name != "PortfolioFinancialFlowObservations"
            or request.product_version != "v1"
            or request.page_index != 0
            or request.page_token is not None
            or request.expected_content_hash != selector.manifest_hash
            or request.source_revision != str(selector.cut_revision)
            or request.currency != selector.currency
        ):
            raise SourceCaptureUnavailable("SOURCE_NATIVE_FLOW_SELECTION_MISMATCH")
        async with self.sessions() as session:
            row = await session.scalar(
                select(FlowSourceCutRow).where(
                    FlowSourceCutRow.tenant_id == request.tenant_id,
                    FlowSourceCutRow.portfolio_id == request.portfolio_id,
                    FlowSourceCutRow.source_system == selector.source_system,
                    FlowSourceCutRow.source_cut_id == selector.source_cut_id,
                    FlowSourceCutRow.cut_revision == selector.cut_revision,
                    FlowSourceCutRow.manifest_hash == selector.manifest_hash,
                    FlowSourceCutRow.receipt_job_id == request.receipt_job_id,
                )
            )
            if row is None:
                raise SourceCaptureUnavailable("SOURCE_NATIVE_FLOW_CUT_UNAVAILABLE")
            cut = cut_from_row(row)
            if (cut.coverage_from, cut.coverage_to, cut.currency) != (
                selector.from_date,
                selector.to_date,
                request.currency,
            ):
                raise SourceCaptureUnavailable("SOURCE_NATIVE_FLOW_WINDOW_MISMATCH")
            job = await session.scalar(
                select(IngestionJob).where(
                    IngestionJob.tenant_id == request.tenant_id,
                    IngestionJob.job_id == row.receipt_job_id,
                )
            )
            receipt = completed_source_receipt(
                row,
                job,
                request,
                endpoint="/ingest/portfolio-flow-source-cuts",
                entity_type="portfolio_flow_source_cut",
            )
            records = {}
            pins = cut.event_pins + cut.dependency_pins
            # Existing flow-v1 membership limit is retained; acquire via bounded
            # indexed reads and validate its existing exact reversal closure.
            for first in range(0, len(pins), 250):
                selected = pins[first : first + 250]
                pairs = (
                    await session.execute(
                        select(FlowEventObservationRow, IngestionJob)
                        .join(
                            IngestionJob,
                            and_(
                                IngestionJob.tenant_id == FlowEventObservationRow.tenant_id,
                                IngestionJob.job_id == FlowEventObservationRow.receipt_job_id,
                            ),
                        )
                        .where(
                            FlowEventObservationRow.tenant_id == request.tenant_id,
                            FlowEventObservationRow.portfolio_id == request.portfolio_id,
                            FlowEventObservationRow.producer_id == cut.source_system,
                            FlowEventObservationRow.observation_id.in_(
                                [pin.observation_id for pin in selected]
                            ),
                        )
                        .limit(250)
                    )
                ).all()
                if len(pairs) != len(selected):
                    raise SourceCaptureUnavailable("SOURCE_NATIVE_FLOW_MEMBERSHIP_INCOMPLETE")
                for event_row, event_job in pairs:
                    fact = flow_from_row(event_row)
                    event_receipt = completed_source_receipt(
                        event_row,
                        event_job,
                        request,
                        endpoint="/ingest/portfolio-flow-event-observations",
                        entity_type="portfolio_flow_event_observation",
                    )
                    records[fact.content_hash] = (
                        fact,
                        {
                            "fact": TypeAdapter(type(fact)).dump_python(fact, mode="json"),
                            "received_at": event_row.received_at.isoformat(),
                            "receipt": event_receipt,
                        },
                    )
            events = tuple(records[pin.observation_id][0] for pin in cut.event_pins)
            dependencies = tuple(records[pin.observation_id][0] for pin in cut.dependency_pins)
            if not require_flow_cut_events(cut, events, dependencies):
                raise SourceCaptureUnavailable("SOURCE_NATIVE_FLOW_COVERAGE_UNAVAILABLE")
            payload = {
                "product_name": request.product_name,
                "product_version": "v1",
                "cut": TypeAdapter(type(cut)).dump_python(cut, mode="json"),
                "events": [records[pin.observation_id][1] for pin in cut.event_pins],
                "dependencies": [records[pin.observation_id][1] for pin in cut.dependency_pins],
                "received_at": row.received_at.isoformat(),
                "receipt": receipt,
            }
        return await self._page(request, payload, cut.content_hash, total=len(pins))

    async def _valuation(self, request, selector):
        if (
            request.role not in {InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS}
            or request.product_name != "PortfolioTimeseriesInput"
            or request.product_version != "v1"
            or request.page_index != 0
            or request.page_token is not None
            or selector.export_job_id is None
            or selector.export_content_hash is None
            or request.receipt_job_id != selector.export_job_id
            or request.source_revision != selector.export_job_id
            or request.expected_content_hash != selector.export_content_hash
            or request.currency != selector.reporting_currency
        ):
            raise SourceCaptureUnavailable("SOURCE_NATIVE_RETAINED_VALUATION_REQUIRED")
        async with self.sessions() as session:
            row = await session.scalar(
                select(AnalyticsExportJob)
                .join(
                    Portfolio,
                    Portfolio.portfolio_id == AnalyticsExportJob.portfolio_id,
                )
                .where(
                    Portfolio.tenant_id == request.tenant_id,
                    AnalyticsExportJob.portfolio_id == request.portfolio_id,
                    AnalyticsExportJob.job_id == selector.export_job_id,
                )
            )
            if row is None:
                raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_UNAVAILABLE")
            epoch, scope, count = validate_retained_valuation(row, request, selector)
            payload = {
                "product_name": request.product_name,
                "product_version": "v1",
                "result": row.result_payload,
                "request": row.request_payload,
                "receipt": {
                    "job_id": row.job_id,
                    "status": row.status,
                    "dataset_type": row.dataset_type,
                    "portfolio_id": row.portfolio_id,
                    "completed_at": row.completed_at.isoformat(),
                    "result_row_count": row.result_row_count,
                },
            }
        return await self._page(
            request,
            payload,
            request.expected_content_hash,
            total=count,
            snapshot_epoch=str(epoch),
            request_scope=scope,
            export_job_id=row.job_id,
            refresh_of_job_id=selector.refresh_of_job_id,
        )

    async def _page(
        self,
        request,
        payload,
        typed_hash,
        *,
        total,
        snapshot_epoch=None,
        request_scope=None,
        export_job_id=None,
        refresh_of_job_id=None,
    ):
        serializer = NATIVE_FACT_SERIALIZERS[request.role]
        if native_capture_typed_root(serializer, payload) != typed_hash:
            raise SourceCaptureUnavailable("SOURCE_NATIVE_CAPTURE_ROOT_DRIFT")
        owned = await acquire_native_source_bytes(payload, serializer)
        try:
            return CapturedSourcePage(
                request,
                owned,
                serializer,
                "application/json",
                typed_hash,
                snapshot_epoch,
                request_scope,
                total,
                total,
                None,
                request.receipt_job_id,
                datetime.now(UTC),
                "v1",
                export_job_id,
                refresh_of_job_id,
            )
        except BaseException:
            owned.close()
            raise

    async def close(self):
        # Factory owns the shared engine; this adapter may never dispose another worker's pool.
        return None


async def acquire_native_source_bytes(payload, serializer):
    """Stream exactly source_product_bytes' canonical wrapper into a bounded-memory spool."""

    async def chunks():
        buffer = bytearray()
        encoder = json.JSONEncoder(
            sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        )
        for text in encoder.iterencode({"serializer": serializer, "payload": payload}):
            encoded = text.encode("utf-8")
            start = 0
            while start < len(encoded):
                take = min(524288 - len(buffer), len(encoded) - start)
                buffer.extend(encoded[start : start + take])
                start += take
                if len(buffer) == 524288:
                    yield bytes(buffer)
                    buffer.clear()
        if buffer:
            yield bytes(buffer)

    return await SourceCaptureBytes.acquire(chunks())


def _require_export_completion(row, request, selector):
    result, original = row.result_payload, row.request_payload
    if (
        row.status != "completed"
        or row.completed_at is None
        or row.completed_at.utcoffset() is None
        or row.dataset_type != "portfolio_timeseries"
        or type(result) is not dict
        or type(original) is not dict
        or row.job_id != request.receipt_job_id
        or row.portfolio_id != request.portfolio_id
        or original.get("portfolio_id") != request.portfolio_id
        or original.get("dataset_type") != "portfolio_timeseries"
        or original.get("refresh_of_job_id") != selector.refresh_of_job_id
        or result.get("job_id") != row.job_id
        or result.get("dataset_type") != "portfolio_timeseries"
    ):
        raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_COMPLETION_MISMATCH")
    return result, original


def _require_export_identity(result, request):
    data, evidence = result.get("data"), result.get("source_evidence")
    if (
        type(data) is not list
        or type(evidence) is not dict
        or evidence.get("availability") != "RETAINED"
    ):
        raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_EVIDENCE_UNAVAILABLE")
    pages = evidence.get("pages")
    if type(pages) is not list or not pages:
        raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_PAGE_EVIDENCE_MISSING")
    for page in pages:
        if (
            type(page) is not dict
            or not {"source_metadata", "requested_scope", "page_number", "row_count"} <= set(page)
            or type(page["source_metadata"]) is not dict
            or type(page["requested_scope"]) is not dict
            or type(page["source_metadata"].get("page")) is not dict
        ):
            raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_PAGE_EVIDENCE_MALFORMED")
    digest = export_source_selection_digest(data, evidence)
    if (
        digest != "sha256:" + request.expected_content_hash
        or evidence.get("selection_digest") != digest
    ):
        raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_SELECTION_DRIFT")
    return data, pages


def _require_export_business_scope(metadata, requested, original, request, selector):
    original_request = original.get("portfolio_timeseries_request")
    if (
        type(original_request) is not dict
        or {key: value for key, value in original_request.items() if key != "page"} != requested
    ):
        raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_ORIGINAL_REQUEST_MISMATCH")
    window = {
        "start_date": selector.from_date.isoformat(),
        "end_date": selector.to_date.isoformat(),
    }
    expected_metadata = {
        "tenant_id": request.tenant_id,
        "portfolio_id": request.portfolio_id,
        "reporting_currency": request.currency,
        "resolved_window": window,
        "data_quality_status": "COMPLETE",
        "freshness_status": "CURRENT",
    }
    expected_request = {
        "as_of_date": selector.as_of_date.isoformat(),
        "window": window,
        "reporting_currency": request.currency,
        "consumer_system": selector.consumer_system,
    }
    if (
        {key: metadata.get(key) for key in expected_metadata} != expected_metadata
        or {key: requested.get(key) for key in expected_request} != expected_request
        or requested.get("period") is not None
        or metadata.get("source_evidence_current") is not True
    ):
        raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_PAGE_SCOPE_MISMATCH")


def _require_export_page_position(page, index):
    paging = page["source_metadata"]["page"]
    epoch, scope = paging.get("snapshot_epoch"), paging.get("request_scope_fingerprint")
    if (
        page["page_number"] != index + 1
        or type(page["row_count"]) is not int
        or page["row_count"] < 0
        or page["row_count"] != paging.get("returned_row_count")
        or type(epoch) is not int
        or epoch < 0
        or type(scope) is not str
        or not scope
    ):
        raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_PAGE_SCOPE_MISMATCH")
    return epoch, scope


def _require_export_cursor(page, *, final, previous_tokens):
    token = page["source_metadata"]["page"].get("next_page_token")
    if final:
        if token is not None:
            raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_INCOMPLETE_TRAVERSAL")
    elif type(token) is not str or not token or token in previous_tokens or page["row_count"] == 0:
        raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_CURSOR_NO_PROGRESS")
    else:
        previous_tokens.add(token)


def validate_retained_valuation(row, request, selector):
    """Reconcile native completion, typed identity, business scope and traversal separately."""
    result, original = _require_export_completion(row, request, selector)
    data, pages = _require_export_identity(result, request)
    epoch, scope, count = None, None, 0
    previous_tokens: set[str] = set()
    for index, page in enumerate(pages):
        _require_export_business_scope(
            page["source_metadata"], page["requested_scope"], original, request, selector
        )
        actual_epoch, actual_scope = _require_export_page_position(page, index)
        if index and (actual_epoch, actual_scope) != (epoch, scope):
            raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_MIXED_EPOCH_OR_SCOPE")
        epoch, scope = actual_epoch, actual_scope
        count += page["row_count"]
        _require_export_cursor(page, final=index == len(pages) - 1, previous_tokens=previous_tokens)
    if (
        count != len(data)
        or row.result_row_count != count
        or result.get("result_row_count") != count
    ):
        raise SourceCaptureUnavailable("SOURCE_NATIVE_EXPORT_ROW_COUNT_MISMATCH")
    return epoch, scope, count
