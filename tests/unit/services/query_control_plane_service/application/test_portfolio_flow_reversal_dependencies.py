"""Prior-window dependency evidence never becomes a current-window flow amount."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from portfolio_common.page_tokens import PageTokenCodec

from src.services.query_control_plane_service.app.application import (
    portfolio_flow_source_observations as application,
)
from src.services.query_control_plane_service.app.contracts import (
    portfolio_flow_source_observations as contracts,
)
from src.services.query_control_plane_service.app.ports.portfolio_flow_source_observations import (
    PersistedFlowCut,
    PersistedFlowEvent,
)
from tests.test_support.portfolio_flow_source_fixtures import cut, dated_event, event, pin

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_verified_cross_window_example_binds_complete_actual_serialization():
    import json
    from pathlib import Path

    from portfolio_common.logging_utils import correlation_id_var

    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    example = next(
        e
        for e in json.loads((root / "docs/standards/verified-api-examples.v1.json").read_text())[
            "examples"
        ]
        if e["id"] == "portfolio-flow-source-cross-window-reversal"
    )
    assert example["dynamicFieldPointers"] == ["/generated_at"]
    record, _ = _fixture()
    request = contracts.PortfolioFlowObservationsRequest.model_validate(example["request"]["body"])
    service = application.PortfolioFlowObservationsService(
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
    actual["generated_at"] = example["response"]["body"]["generated_at"]
    assert actual == example["response"]["body"]


class Reader:
    def __init__(self, record):
        self.record = record

    async def read_cut(self, **kwargs):
        return self.record


def _fixture():
    target = dated_event("december", date(2025, 12, 15), amount=Decimal("9000"))
    reversal = event(
        "january-reversal",
        amount=Decimal("-7.50"),
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="december",
        reversal_target=pin(target),
    )
    january = event("january-cash", amount=Decimal("25"))
    manifest = cut(january, reversal, dependency_pins=(pin(target),))
    admitted = datetime(2026, 10, 15, tzinfo=UTC)
    record = PersistedFlowCut(
        manifest,
        admitted,
        "cut-receipt",
        tuple(
            PersistedFlowEvent(f, admitted, "receipt-" + f.envelope.source_record_id)
            for f in (january, reversal)
        ),
        (PersistedFlowEvent(target, admitted, "december-receipt"),),
    )
    request = contracts.PortfolioFlowObservationsRequest.model_validate(
        {
            "source_system": manifest.source_system,
            "source_cut_id": manifest.source_cut_id,
            "cut_revision": 1,
            "manifest_hash": manifest.content_hash,
            "currency": manifest.currency,
            "window": {"from_date": manifest.coverage_from, "to_date": manifest.coverage_to},
            "page": {"page_size": 1},
        }
    )
    return record, request


async def test_cross_window_dependency_amounts_excluded_and_both_sets_bind_cursor():
    record, request = _fixture()
    manifest = record.cut
    target = record.dependencies[0].fact
    admitted = record.received_at
    service = application.PortfolioFlowObservationsService(
        Reader(record), PageTokenCodec(secret="synthetic-page")
    )
    first = await service.query(
        tenant_id=manifest.tenant_id, portfolio_id=manifest.portfolio_id, request=request
    )
    assert first.source_fields_available and not first.authoritative_use_available
    assert first.pagination.total_count == 2 and first.pagination.dependency_count == 1
    assert [e.amount for e in first.events] == ["25"]
    assert first.reversal_dependencies[0].amount == "9000"
    next_request = request.model_copy(
        update={
            "page": request.page.model_copy(update={"page_token": first.pagination.next_page_token})
        }
    )
    last = await service.query(
        tenant_id=manifest.tenant_id, portfolio_id=manifest.portfolio_id, request=next_request
    )
    assert (
        last.events[0].amount == "-7.50"
        and last.events[0].reversal_target.observation_id == target.content_hash
    )
    assert last.pagination.ordered_set_hash == first.pagination.ordered_set_hash
    assert last.pagination.dependency_set_hash == first.pagination.dependency_set_hash
    assert last.pagination.next_page_token is None
    service.reader = Reader(replace(record, dependencies=()))
    with pytest.raises(ValueError, match="incomplete"):
        await service.query(
            tenant_id=manifest.tenant_id, portfolio_id=manifest.portfolio_id, request=next_request
        )
    changed_receipt = replace(record.dependencies[0], received_at=admitted + timedelta(seconds=1))
    service.reader = Reader(replace(record, dependencies=(changed_receipt,)))
    with pytest.raises(ValueError, match="cursor"):
        await service.query(
            tenant_id=manifest.tenant_id, portfolio_id=manifest.portfolio_id, request=next_request
        )
