"""Actual fact reconstruction and correct-family receipt checks with mocked sessions."""

import json
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.analytics_export_source_identity import export_source_selection_digest
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import InputRole, source_product_bytes
from portfolio_common.domain.portfolio_flow_source_observations import (
    FlowEventObservation,
    FlowEventPin,
    FlowSourceCut,
)
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationCoverage,
    ObservationEnvelope,
)
from portfolio_common.portfolio_financial_source_cut_admission import (
    FlowSourceSelector,
    ObservationSourceSelector,
    ValuationSelector,
)
from portfolio_common.portfolio_flow_source_observation_models import (
    FlowEventObservationRow,
    FlowSourceCutRow,
    cut_values,
)
from portfolio_common.portfolio_source_observation_models import (
    CashAvailabilityObservationRow,
    FundingInvestmentObservationRow,
)

from src.services.persistence_service.app.infrastructure.financial_source_capture_client import (
    NativeFinancialSourceCaptureClient,
    acquire_native_source_bytes,
    validate_retained_valuation,
)
from src.services.persistence_service.app.ports.financial_source_captures import (
    SourceCaptureRequest,
    SourceCaptureUnavailable,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def source():
    stamp = datetime(2026, 10, 16, tzinfo=UTC)
    envelope = ObservationEnvelope(
        "tenant",
        "portfolio",
        "producer",
        "record",
        1,
        "cut",
        "v1",
        date(2025, 1, 1),
        None,
        stamp,
        stamp,
        ObservationCoverage.COMPLETE,
        "declared-scope",
    )
    fact = CashAvailabilityObservation(envelope, "USD", Decimal("0.00"), None, None)
    row = CashAvailabilityObservationRow(
        **(asdict(envelope) | {"coverage": "complete"}),
        currency="USD",
        settled_amount=fact.settled,
        encumbered_amount=None,
        available_amount=None,
        observation_id=fact.content_hash,
        content_hash=fact.content_hash,
        receipt_job_id="receipt",
        received_at=stamp,
    )
    selector = ObservationSourceSelector(
        kind="CASH",
        as_of_date=date(2025, 1, 31),
        producer_id="producer",
        source_record_id="record",
        observation_id=fact.content_hash,
        content_hash=fact.content_hash,
        source_cut_id="cut",
        source_version=1,
    )
    request = SourceCaptureRequest(
        "tenant",
        "portfolio",
        InputRole.CASH,
        "PortfolioFinancialSourceObservations",
        "v1",
        selector.model_dump_json().encode(),
        canonical_content_hash(selector.model_dump(mode="json")),
        fact.content_hash,
        "receipt",
        "1",
        None,
        currency="USD",
    )
    job = SimpleNamespace(
        tenant_id="tenant",
        job_id="receipt",
        status="completed",
        completed_at=stamp,
        endpoint="/ingest/portfolio-cash-availability-observations",
        entity_type="portfolio_cash_availability_observation",
        accepted_count=1,
    )
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[row, job]))

    @asynccontextmanager
    async def sessions():
        yield session

    return request, row, job, NativeFinancialSourceCaptureClient(sessions), session


async def test_complete_native_fact_reconstructs_exact_domain_root_and_keeps_unknown_epoch():
    request, _, _, client, session = source()
    page = await client.fetch(request)
    try:
        body = json.loads(b"".join(page.capture_bytes.segments()))
        assert body["serializer"] == "portfolio-cash-availability:domain-json:v1"
        assert body["payload"]["fact"]["settled"] == "0.00"
        assert body["payload"]["fact"]["available"] is None
        assert body["payload"]["fact"]["envelope"]["predecessor_id"] is None
        assert page.typed_content_hash == request.expected_content_hash
        assert page.snapshot_epoch is page.request_scope is None
        assert page.completed_receipt_id == "receipt"
        assert session.scalar.await_count == 2
    finally:
        page.capture_bytes.close()


@pytest.mark.parametrize(
    "mutation", ["failed", "family", "tenant", "time", "currency", "raw_fact", "coverage"]
)
async def test_wrong_receipt_scope_or_fact_never_earns_capture(mutation):
    request, row, job, client, _ = source()
    if mutation == "failed":
        job.status = "accepted"
    elif mutation == "family":
        job.endpoint = "/ingest/portfolio-funding-investment-observations"
    elif mutation == "tenant":
        job.tenant_id = "foreign"
    elif mutation == "time":
        job.completed_at = None
    elif mutation == "currency":
        row.currency = "SGD"
    elif mutation == "coverage":
        row.coverage = "partial"
    else:
        row.settled_amount = Decimal("1")
    with pytest.raises(SourceCaptureUnavailable):
        await client.fetch(request)


@pytest.mark.parametrize("delta", [-1, 0, 1])
async def test_actual_native_receipt_completion_may_equal_or_follow_but_never_precede_received(
    delta,
):
    request, row, job, client, _ = source()
    job.completed_at = row.received_at + timedelta(seconds=delta)
    if delta < 0:
        with pytest.raises(SourceCaptureUnavailable, match="COMPLETED_RECEIPT_REQUIRED"):
            await client.fetch(request)
    else:
        page = await client.fetch(request)
        page.capture_bytes.close()


async def test_actual_source_receipt_chronology_requires_aware_received_time():
    request, row, _, client, _ = source()
    row.received_at = row.received_at.replace(tzinfo=None)
    with pytest.raises(SourceCaptureUnavailable):
        await client.fetch(request)


async def test_native_readiness_preserves_unknown_and_false_independently():
    request, cash, job, client, session = source()
    envelope = ObservationEnvelope(
        **{
            key: ObservationCoverage.COMPLETE if key == "coverage" else getattr(cash, key)
            for key in ObservationEnvelope.__dataclass_fields__
        }
    )
    fact = FundingInvestmentObservation(envelope, None, False)
    row = FundingInvestmentObservationRow(
        **(asdict(envelope) | {"coverage": "complete"}),
        funded=None,
        invested=False,
        observation_id=fact.content_hash,
        content_hash=fact.content_hash,
        receipt_job_id="receipt",
        received_at=cash.received_at,
    )
    selector = ObservationSourceSelector.model_validate_json(request.selector_json).model_copy(
        update={
            "kind": "READINESS",
            "observation_id": fact.content_hash,
            "content_hash": fact.content_hash,
        }
    )
    request = replace(
        request,
        role=InputRole.READINESS,
        selector_json=selector.model_dump_json().encode(),
        selector_hash=canonical_content_hash(selector.model_dump(mode="json")),
        expected_content_hash=fact.content_hash,
    )
    job.endpoint, job.entity_type = (
        "/ingest/portfolio-funding-investment-observations",
        "portfolio_funding_investment_observation",
    )
    session.scalar.side_effect = [row, job]
    page = await client.fetch(request)
    try:
        fact_json = json.loads(b"".join(page.capture_bytes.segments()))["payload"]["fact"]
        assert fact_json["funded"] is None and fact_json["invested"] is False
        assert page.snapshot_epoch is None
    finally:
        page.capture_bytes.close()


def flow_source():
    _, cash, _, _, _ = source()
    envelope = ObservationEnvelope(
        **{
            key: ObservationCoverage.COMPLETE if key == "coverage" else getattr(cash, key)
            for key in ObservationEnvelope.__dataclass_fields__
        }
    )
    fact = FlowEventObservation(
        envelope,
        date(2025, 1, 31),
        "USD",
        Decimal("-10.00"),
        "EXTERNAL_CASH",
        "POSTED",
        "NONE",
        None,
        None,
    )
    pin = FlowEventPin("record", fact.content_hash, fact.content_hash, 1)
    cut = FlowSourceCut(
        "tenant",
        "portfolio",
        "producer",
        "flow-cut",
        1,
        "v1",
        "USD",
        date(2025, 1, 1),
        date(2025, 1, 31),
        ObservationCoverage.COMPLETE,
        (pin,),
        (),
        None,
        None,
    )
    row = FlowSourceCutRow(
        **cut_values(cut),
        manifest_hash=cut.content_hash,
        receipt_job_id="cut-receipt",
        received_at=cash.received_at,
    )
    event = FlowEventObservationRow(
        **(asdict(envelope) | {"coverage": "complete"}),
        business_date=fact.business_date,
        currency="USD",
        amount=fact.amount,
        classification="EXTERNAL_CASH",
        posting_state="POSTED",
        reversal_state="NONE",
        reverses_event_id=None,
        reversal_target=None,
        economic_event_id=None,
        transaction_id=None,
        content_hash=fact.content_hash,
        observation_id=fact.content_hash,
        receipt_job_id="event-receipt",
        received_at=cash.received_at,
    )
    job = SimpleNamespace(
        tenant_id="tenant",
        job_id="cut-receipt",
        status="completed",
        completed_at=cash.received_at,
        endpoint="/ingest/portfolio-flow-source-cuts",
        entity_type="portfolio_flow_source_cut",
        accepted_count=1,
    )
    event_job = SimpleNamespace(
        **(
            vars(job)
            | {
                "job_id": "event-receipt",
                "endpoint": "/ingest/portfolio-flow-event-observations",
                "entity_type": "portfolio_flow_event_observation",
            }
        )
    )
    selector = FlowSourceSelector(
        kind="FLOWS",
        source_system="producer",
        source_cut_id="flow-cut",
        cut_revision=1,
        manifest_hash=cut.content_hash,
        from_date=cut.coverage_from,
        to_date=cut.coverage_to,
        currency="USD",
    )
    request = SourceCaptureRequest(
        "tenant",
        "portfolio",
        InputRole.FLOWS,
        "PortfolioFinancialFlowObservations",
        "v1",
        selector.model_dump_json().encode(),
        canonical_content_hash(selector.model_dump(mode="json")),
        cut.content_hash,
        "cut-receipt",
        "1",
        None,
        currency="USD",
    )
    result = MagicMock()
    result.all.return_value = [(event, event_job)]
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[row, job]), execute=AsyncMock(return_value=result)
    )

    @asynccontextmanager
    async def sessions():
        yield session

    return request, event_job, result, NativeFinancialSourceCaptureClient(sessions)


async def test_complete_flow_capture_reuses_existing_cut_and_full_domain_envelope():
    request, _, _, client = flow_source()
    page = await client.fetch(request)
    try:
        value = json.loads(b"".join(page.capture_bytes.segments()))
        assert value["payload"]["events"][0]["fact"]["envelope"]["effective_from"] == "2025-01-01"
        assert value["payload"]["events"][0]["fact"]["amount"] == "-10.00"
        assert page.typed_content_hash == request.expected_content_hash
        assert page.returned_count == page.total_count == 1
        assert page.snapshot_epoch is None
    finally:
        page.capture_bytes.close()


@pytest.mark.parametrize("missing", [False, True])
async def test_flow_missing_member_or_wrong_event_receipt_refuses(missing):
    request, event_job, result, client = flow_source()
    if missing:
        result.all.return_value = []
    else:
        event_job.entity_type = "portfolio_cash_availability_observation"
    with pytest.raises(SourceCaptureUnavailable):
        await client.fetch(request)


def valuation_source():
    window = {"start_date": "2025-01-31", "end_date": "2025-01-31"}
    requested = {
        "as_of_date": "2025-01-31",
        "window": window,
        "period": None,
        "reporting_currency": "USD",
        "consumer_system": "lotus-manage",
    }
    evidence = {
        "selection_digest": None,
        "availability": "RETAINED",
        "pages": [
            {
                "page_number": 1,
                "row_count": 1,
                "requested_scope": requested,
                "source_metadata": {
                    "tenant_id": "tenant",
                    "portfolio_id": "portfolio",
                    "reporting_currency": "USD",
                    "resolved_window": window,
                    "data_quality_status": "COMPLETE",
                    "source_evidence_current": True,
                    "freshness_status": "CURRENT",
                    "page": {
                        "snapshot_epoch": 7,
                        "request_scope_fingerprint": "actual-scope",
                        "returned_row_count": 1,
                        "next_page_token": None,
                    },
                },
            }
        ],
    }
    data = [{"valuation_date": "2025-01-31", "eod_market_value": "100.00"}]
    digest = export_source_selection_digest(data, evidence)
    evidence["selection_digest"] = digest
    result = {
        "job_id": "export",
        "dataset_type": "portfolio_timeseries",
        "result_row_count": 1,
        "source_evidence": evidence,
        "data": data,
    }
    row = SimpleNamespace(
        job_id="export",
        portfolio_id="portfolio",
        dataset_type="portfolio_timeseries",
        status="completed",
        completed_at=datetime(2026, 10, 16, tzinfo=UTC),
        result_row_count=1,
        result_payload=result,
        request_payload={
            "portfolio_id": "portfolio",
            "dataset_type": "portfolio_timeseries",
            "portfolio_timeseries_request": requested,
        },
    )
    selector = ValuationSelector(
        kind="VALUATION",
        as_of_date=date(2025, 1, 31),
        from_date=date(2025, 1, 31),
        to_date=date(2025, 1, 31),
        reporting_currency="USD",
        consumer_system="lotus-manage",
        export_job_id="export",
        export_content_hash=digest[7:],
        refresh_of_job_id=None,
    )
    request = SourceCaptureRequest(
        "tenant",
        "portfolio",
        InputRole.MONTH_END_ASSETS,
        "PortfolioTimeseriesInput",
        "v1",
        selector.model_dump_json().encode(),
        canonical_content_hash(selector.model_dump(mode="json")),
        digest[7:],
        "export",
        "export",
        None,
        currency="USD",
    )
    return row, request, selector


async def test_actual_retained_export_context_and_shared_typed_root_are_required():
    row, request, selector = valuation_source()
    assert validate_retained_valuation(row, request, selector) == (7, "actual-scope", 1)
    session = SimpleNamespace(scalar=AsyncMock(return_value=row))

    @asynccontextmanager
    async def sessions():
        yield session

    page = await NativeFinancialSourceCaptureClient(sessions).fetch(request)
    try:
        assert page.snapshot_epoch == "7" and page.request_scope == "actual-scope"
        assert page.export_job_id == "export" and page.completed_receipt_id == "export"
    finally:
        page.capture_bytes.close()


@pytest.mark.parametrize(
    "mutation", ["tenant", "epoch", "incomplete", "count", "legacy", "raw_root", "uncompleted"]
)
async def test_valution_missing_or_contradictory_retained_context_never_fabricates_proof(mutation):
    row, request, selector = valuation_source()
    metadata = row.result_payload["source_evidence"]["pages"][0]["source_metadata"]
    if mutation == "tenant":
        metadata["tenant_id"] = "foreign"
    elif mutation == "epoch":
        metadata["page"]["snapshot_epoch"] = None
    elif mutation == "incomplete":
        metadata["page"]["next_page_token"] = "still-pending"
    elif mutation == "count":
        row.result_row_count = 2
    elif mutation == "legacy":
        row.result_payload["source_evidence"]["availability"] = "UNAVAILABLE"
    elif mutation == "raw_root":
        row.result_payload["data"][0]["eod_market_value"] = "101.00"
    else:
        row.completed_at = None
    if mutation in {"tenant", "epoch"}:
        # A self-consistent content digest cannot excuse contradictory native scope.
        digest = export_source_selection_digest(
            row.result_payload["data"], row.result_payload["source_evidence"]
        )
        row.result_payload["source_evidence"]["selection_digest"] = digest
        request = replace(request, expected_content_hash=digest[7:])
    with pytest.raises(SourceCaptureUnavailable):
        validate_retained_valuation(row, request, selector)


async def test_streaming_serializer_matches_original_exact_wrapper_with_large_payload():
    payload = {"unicode": "\u6e2c\u8a66", "rows": ["a" * 524288] * 5}
    owned = await acquire_native_source_bytes(payload, "synthetic-native:v1")
    try:
        assert b"".join(owned.segments()) == source_product_bytes(
            payload, serializer="synthetic-native:v1"
        )
        assert owned._stream._rolled
    finally:
        owned.close()
