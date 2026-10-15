"""Pinned traversal stays stable across late arrival and source correction."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from portfolio_common.page_tokens import PageTokenCodec

from src.services.query_control_plane_service.app.application import (
    portfolio_flow_source_observations as flow_application,
)
from src.services.query_control_plane_service.app.contracts import (
    portfolio_flow_source_observations as flow_contracts,
)
from src.services.query_control_plane_service.app.ports.portfolio_flow_source_observations import (
    PersistedFlowCut,
    PersistedFlowEvent,
)
from tests.test_support.portfolio_flow_source_fixtures import cut as make_cut
from tests.test_support.portfolio_flow_source_fixtures import event

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_verified_flow_example_binds_complete_actual_serialization():
    import json
    from pathlib import Path

    from portfolio_common.logging_utils import correlation_id_var

    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    catalog = json.loads((root / "docs/standards/verified-api-examples.v1.json").read_text())
    example = next(
        e for e in catalog["examples"] if e["id"] == "portfolio-flow-source-complete-unqualified"
    )
    assert example["dynamicFieldPointers"] == ["/generated_at"]
    record, _ = _fixture()
    request = flow_contracts.PortfolioFlowObservationsRequest.model_validate(
        example["request"]["body"]
    )
    service = flow_application.PortfolioFlowObservationsService(
        Reader(record), PageTokenCodec(secret="synthetic-page")
    )
    token = correlation_id_var.set("synthetic-correlation")
    try:
        actual = (
            await service.query(
                tenant_id=record.cut.tenant_id,
                portfolio_id=record.cut.portfolio_id,
                request=request,
            )
        ).model_dump(mode="json")
    finally:
        correlation_id_var.reset(token)
    assert datetime.fromisoformat(actual["generated_at"]).tzinfo is not None
    actual["generated_at"] = example["response"]["body"]["generated_at"]
    assert actual == example["response"]["body"]


def _fixture():
    facts = (event("a"), event("b"), event("c"))
    cut = make_cut(*facts)
    admitted = datetime(2026, 10, 15, tzinfo=UTC)
    record = PersistedFlowCut(
        cut,
        admitted,
        "cut-receipt",
        tuple(
            PersistedFlowEvent(f, admitted, "receipt-" + f.envelope.source_record_id) for f in facts
        ),
    )
    request = flow_contracts.PortfolioFlowObservationsRequest.model_validate(
        {
            "source_system": cut.source_system,
            "source_cut_id": cut.source_cut_id,
            "cut_revision": 1,
            "manifest_hash": cut.content_hash,
            "currency": "SGD",
            "window": {"from_date": "2026-01-01", "to_date": "2026-01-31"},
            "page": {"page_size": 2},
        }
    )
    return record, request


class Reader:
    def __init__(self, record):
        self.record = record

    async def read_cut(self, **kwargs):
        return self.record

    async def read_event(self, **kwargs):
        return self.record.events[0] if self.record else None


async def test_full_set_digest_count_terminal_cursor_and_actual_receipt_are_preserved():
    record, request = _fixture()
    service = flow_application.PortfolioFlowObservationsService(
        Reader(record), PageTokenCodec(secret="unit-synthetic")
    )
    first = await service.query(
        tenant_id=record.cut.tenant_id, portfolio_id=record.cut.portfolio_id, request=request
    )
    assert first.source_fields_available and not first.authoritative_use_available
    assert [e.source_record_id for e in first.events] == ["a", "b"]
    assert first.pagination.total_count == 3
    assert first.events[0].received_at == datetime(2026, 10, 15, tzinfo=UTC)
    assert first.events[0].business_date.isoformat() == "2026-01-02"
    assert first.events[0].amount == "10.001000000000000000001"
    request = request.model_copy(
        update={
            "page": request.page.model_copy(
                update={
                    "page_token": first.pagination.next_page_token,
                }
            )
        }
    )
    last = await service.query(
        tenant_id=record.cut.tenant_id, portfolio_id=record.cut.portfolio_id, request=request
    )
    assert [e.source_record_id for e in last.events] == ["c"]
    assert last.pagination.offset == 2 and last.pagination.returned_count == 1
    assert last.pagination.next_page_token is None
    assert last.pagination.ordered_set_hash == first.pagination.ordered_set_hash


async def test_tampered_cursor_currency_window_and_foreign_scope_refused():
    record, request = _fixture()
    codec = PageTokenCodec(secret="unit-synthetic")
    service = flow_application.PortfolioFlowObservationsService(Reader(record), codec)
    first = await service.query(
        tenant_id=record.cut.tenant_id, portfolio_id=record.cut.portfolio_id, request=request
    )
    for altered in (
        request.model_copy(update={"currency": "USD"}),
        request.model_copy(
            update={
                "window": request.window.model_copy(update={"to_date": record.cut.coverage_from})
            }
        ),
        request.model_copy(
            update={
                "page": request.page.model_copy(
                    update={"page_token": first.pagination.next_page_token[:-4] + "AAAA"}
                )
            }
        ),
        request.model_copy(
            update={
                "page": request.page.model_copy(
                    update={"page_token": first.pagination.next_page_token, "page_size": 1}
                )
            }
        ),
    ):
        with pytest.raises(ValueError):
            await service.query(
                tenant_id=record.cut.tenant_id,
                portfolio_id=record.cut.portfolio_id,
                request=altered,
            )
    with pytest.raises(ValueError):
        await service.query(
            tenant_id="foreign", portfolio_id=record.cut.portfolio_id, request=request
        )


async def test_absence_and_missing_pins_cannot_be_complete_empty():
    record, request = _fixture()
    service = flow_application.PortfolioFlowObservationsService(
        Reader(None), PageTokenCodec(secret="unit-synthetic")
    )
    with pytest.raises(LookupError):
        await service.query(
            tenant_id=record.cut.tenant_id, portfolio_id=record.cut.portfolio_id, request=request
        )


async def test_revision_lookup_refuses_foreign_reader_scope_and_exposes_actual_original_pins():
    record, request = _fixture()
    service = flow_application.PortfolioFlowObservationsService(
        Reader(record), PageTokenCodec(secret="synthetic-page")
    )
    selection = dict(
        tenant_id=record.cut.tenant_id,
        portfolio_id=record.cut.portfolio_id,
        source_system=record.cut.source_system,
        source_record_id="a",
        flow_source_record_revision=1,
    )
    evidence = await service.event(**selection)
    assert evidence.observation_id == record.events[0].fact.content_hash
    assert (
        evidence.receipt_job_id == "receipt-a"
        and evidence.received_at == record.events[0].received_at
    )
    for name, value in (
        ("tenant_id", "foreign"),
        ("portfolio_id", "foreign"),
        ("source_system", "foreign"),
        ("source_record_id", "other"),
        ("flow_source_record_revision", 2),
    ):
        with pytest.raises(ValueError, match="scope"):
            await service.event(**{**selection, name: value})
    service.reader = Reader(replace(record, events=record.events[:1]))
    with pytest.raises(ValueError, match="incomplete"):
        await service.query(
            tenant_id=record.cut.tenant_id, portfolio_id=record.cut.portfolio_id, request=request
        )
