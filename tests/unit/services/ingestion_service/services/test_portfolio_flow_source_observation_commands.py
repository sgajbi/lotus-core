"""Flow and empty-cut submissions retain native command/receipt semantics."""

from dataclasses import asdict, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAuthority,
)

from src.services.ingestion_service.app.DTOs.portfolio_source_observation_dto import (
    FlowEventObservationIngestionRequest,
    FlowSourceCutIngestionRequest,
)
from src.services.ingestion_service.app.services.portfolio_source_observation_commands import (
    ObservationSubmission,
    PortfolioSourceObservationCommands,
)
from tests.test_support.portfolio_flow_source_fixtures import cut, event

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def submission(is_cut=False):
    fact = event()
    if is_cut:
        manifest = cut()
        values = asdict(manifest)
        values.pop("tenant_id")
        values["producer_manifest_hash"] = manifest.content_hash
        request = FlowSourceCutIngestionRequest(cuts=[values])
    else:
        values = asdict(fact.envelope)
        values.pop("tenant_id")
        values["source_system"] = values.pop("producer_id")
        values["flow_source_record_revision"] = values.pop("source_revision")
        values["source_record_id"] = values.pop("source_record_id")
        values.update({k: v for k, v in asdict(fact).items() if k != "envelope"})
        values.update(amount=str(fact.amount), content_hash=fact.content_hash)
        request = FlowEventObservationIngestionRequest(observations=[values])
    context = TenantContext(
        TenantId("tenant-synthetic"), service_identity="producer-synthetic", identity_verified=True
    )
    grant = ProducerSubmissionGrant(
        "tenant-synthetic", "portfolio-synthetic", "producer-synthetic", fact.family
    )
    return ObservationSubmission(
        context, request, "unit-flow-idempotency", received_at=datetime.now(UTC)
    ), grant


@pytest.mark.parametrize("is_cut", [False, True])
async def test_native_command_uses_current_internal_time_and_empty_cut_has_own_receipt(is_cut):
    request, grant = submission(is_cut)
    created = []
    job = SimpleNamespace(
        job_id="native-unit-receipt", status="completed", completed_at=datetime.now(UTC)
    )
    service = SimpleNamespace(
        assert_ingestion_writable=AsyncMock(),
        create_or_get_job=AsyncMock(return_value=SimpleNamespace(job=job)),
    )

    def factory(stager):
        created.append(stager)
        return service

    command = PortfolioSourceObservationCommands(
        UnqualifiedProducerAuthority((grant,)),
        factory,
        SimpleNamespace(find_matching_job=AsyncMock(return_value=None)),
    )
    result = await command.submit(request)
    assert result.job_id == "native-unit-receipt"
    stager = created[0]
    assert stager.received_at == request.received_at and stager.cut_request == is_cut
    assert len(stager.facts) == 1 and stager.admissions[0].qualification == "unqualified"
    arguments = service.create_or_get_job.await_args.kwargs
    assert arguments["accepted_count"] == 1
    assert arguments["endpoint"] == (
        "/ingest/portfolio-flow-source-cuts"
        if is_cut
        else "/ingest/portfolio-flow-event-observations"
    )
    assert "received_at" not in arguments["request_payload"]
    if is_cut:
        assert stager.facts[0].event_pins == ()


async def test_same_idempotency_returns_original_receipt_and_untrusted_identity_has_no_effect():
    request, grant = submission()
    original = SimpleNamespace(
        job_id="original", status="completed", completed_at=datetime(2026, 10, 15, tzinfo=UTC)
    )
    service = SimpleNamespace(
        get_job=AsyncMock(return_value=original), create_or_get_job=AsyncMock()
    )
    creations = []

    def factory(stager):
        creations.append(stager)
        return service

    command = PortfolioSourceObservationCommands(
        UnqualifiedProducerAuthority((grant,)),
        factory,
        SimpleNamespace(find_matching_job=AsyncMock(return_value=original)),
    )
    assert await command.submit(request) is original
    service.create_or_get_job.assert_not_awaited()
    with pytest.raises(ObservationConflict, match="NOT_ADMITTED"):
        await command.submit(
            replace(
                request, tenant_context=replace(request.tenant_context, identity_verified=False)
            )
        )
    assert len(creations) == 1
