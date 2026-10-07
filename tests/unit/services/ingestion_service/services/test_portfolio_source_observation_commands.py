"""Admission occurs before receipt/SQL effects; mocked I/O is not financial PG proof."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    ObservationConflict,
    ObservationCoverage,
    ObservationEnvelope,
)
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAuthority,
)

from src.services.ingestion_service.app.DTOs.portfolio_source_observation_dto import (
    CashAvailabilityObservationIngestionRequest,
)
from src.services.ingestion_service.app.services import (
    portfolio_source_observation_commands as module,
)
from src.services.ingestion_service.app.services.portfolio_source_observation_commands import (
    ObservationSubmission,
    PortfolioSourceObservationCommands,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _reader():
    return SimpleNamespace(find_matching_job=AsyncMock(return_value=None))


def _submission():
    envelope = ObservationEnvelope(
        "tenant-synthetic",
        "portfolio-synthetic",
        "producer-synthetic",
        "record",
        1,
        "cut",
        "v1",
        date(2026, 1, 1),
        None,
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, tzinfo=UTC),
        ObservationCoverage.COMPLETE,
        "declared-accounts",
    )
    fact = CashAvailabilityObservation(envelope, "SGD", Decimal("10"), None, Decimal("0"))
    request = CashAvailabilityObservationIngestionRequest.model_validate(
        {
            "observations": [
                {
                    "portfolio_id": envelope.portfolio_id,
                    "source_system": envelope.producer_id,
                    "source_record_id": envelope.source_record_id,
                    "source_version": 1,
                    "source_cut_id": "cut",
                    "definition_version": "v1",
                    "effective_from": envelope.effective_from,
                    "effective_to": None,
                    "observed_at": envelope.observed_at,
                    "generated_at": envelope.generated_at,
                    "coverage": "complete",
                    "coverage_scope": envelope.coverage_scope,
                    "content_hash": fact.content_hash,
                    "currency": "SGD",
                    "settled_amount": "10",
                    "encumbered_amount": None,
                    "available_amount": "0",
                }
            ]
        }
    )
    context = TenantContext(
        TenantId("tenant-synthetic"), service_identity="producer-synthetic", identity_verified=True
    )
    return ObservationSubmission(
        context, request, "synthetic-idempotency", "correlation", "request", "trace"
    ), fact


async def test_default_no_producer_permission_has_no_receipt_or_rate_effect(monkeypatch):
    submission, fact = _submission()
    factory = Mock()
    rate = Mock()
    monkeypatch.setattr(module, "enforce_ingestion_write_rate_limit", rate)
    with pytest.raises(ObservationConflict, match="PRODUCER_NOT_ADMITTED"):
        await PortfolioSourceObservationCommands(
            UnqualifiedProducerAuthority(), factory, _reader()
        ).submit(submission)
    factory.assert_not_called()
    rate.assert_not_called()


async def test_admitted_submission_binds_server_scope_and_atomic_callback_without_async_dispatch(
    monkeypatch,
):
    submission, fact = _submission()
    authority = UnqualifiedProducerAuthority(
        (
            ProducerSubmissionGrant(
                "tenant-synthetic", "portfolio-synthetic", "producer-synthetic", fact.family
            ),
        )
    )
    job = SimpleNamespace(status="completed", completed_at=datetime.now(UTC))
    service = SimpleNamespace(
        assert_ingestion_writable=AsyncMock(),
        create_or_get_job=AsyncMock(return_value=SimpleNamespace(job=job, created=True)),
    )
    factory = Mock(return_value=service)
    monkeypatch.setattr(module, "enforce_ingestion_write_rate_limit", Mock())
    result = await PortfolioSourceObservationCommands(authority, factory, _reader()).submit(
        submission
    )
    assert result is job
    stage = factory.call_args.args[0]
    assert stage.facts == (fact,)
    assert stage.admissions[0].qualification == "unqualified"
    kwargs = service.create_or_get_job.call_args.kwargs
    assert kwargs["tenant_context"] is submission.tenant_context
    assert kwargs["endpoint"] == "/ingest/portfolio-cash-availability-observations"
    assert kwargs["idempotency_key"] == "synthetic-idempotency"
    assert kwargs["request_payload"]["observations"][0]["available_amount"] == "0"


@pytest.mark.parametrize("lineage", [("corr", "req", "trace"), (None, None, None)])
async def test_command_resolves_native_request_lineage_when_submission_has_no_overrides(
    monkeypatch, lineage
):
    submission, fact = _submission()
    submission = replace(submission, correlation_id=None, request_id=None, trace_id=None)
    authority = UnqualifiedProducerAuthority(
        (
            ProducerSubmissionGrant(
                "tenant-synthetic", "portfolio-synthetic", "producer-synthetic", fact.family
            ),
        )
    )
    job = SimpleNamespace(status="completed", completed_at=datetime.now(UTC))
    service = SimpleNamespace(
        assert_ingestion_writable=AsyncMock(),
        create_or_get_job=AsyncMock(return_value=SimpleNamespace(job=job)),
    )
    resolver = Mock(return_value=lineage)
    monkeypatch.setattr(module, "get_request_lineage", resolver)
    monkeypatch.setattr(module, "enforce_ingestion_write_rate_limit", Mock())
    assert (
        await PortfolioSourceObservationCommands(
            authority, lambda stage: service, _reader()
        ).submit(submission)
        is job
    )
    resolver.assert_called_once_with()
    kwargs = service.create_or_get_job.call_args.kwargs
    for key, value in zip(("correlation_id", "request_id", "trace_id"), lineage, strict=True):
        assert kwargs[key] == (value or "")


@pytest.mark.parametrize("status", ["accepted", "queued", "failed"])
async def test_nonterminal_or_failed_receipt_is_not_reported_as_synchronous_success(
    monkeypatch, status
):
    submission, fact = _submission()
    authority = UnqualifiedProducerAuthority(
        (
            ProducerSubmissionGrant(
                "tenant-synthetic", "portfolio-synthetic", "producer-synthetic", fact.family
            ),
        )
    )
    service = SimpleNamespace(
        assert_ingestion_writable=AsyncMock(),
        create_or_get_job=AsyncMock(
            return_value=SimpleNamespace(job=SimpleNamespace(status=status, completed_at=None))
        ),
    )
    monkeypatch.setattr(module, "enforce_ingestion_write_rate_limit", Mock())
    with pytest.raises(ObservationConflict, match="RECEIPT_NOT_COMPLETED"):
        await PortfolioSourceObservationCommands(
            authority, lambda stage: service, _reader()
        ).submit(submission)


@pytest.mark.parametrize(
    "status,completed_at",
    [
        ("completed", datetime(2026, 1, 1, tzinfo=UTC)),
        ("completed", None),
        ("accepted", None),
        ("queued", None),
        ("failed", None),
    ],
)
async def test_matching_replay_precedes_write_controls_but_requires_complete_receipt(
    monkeypatch, status, completed_at
):
    submission, fact = _submission()
    authority = UnqualifiedProducerAuthority(
        (
            ProducerSubmissionGrant(
                "tenant-synthetic", "portfolio-synthetic", "producer-synthetic", fact.family
            ),
        )
    )
    job = SimpleNamespace(status=status, completed_at=completed_at)
    reader = _reader()
    reader.find_matching_job.return_value = SimpleNamespace(job_id="existing", status=status)
    service = SimpleNamespace(
        get_job=AsyncMock(return_value=job),
        assert_ingestion_writable=AsyncMock(side_effect=PermissionError("read-only")),
        create_or_get_job=AsyncMock(),
    )
    rate = Mock(side_effect=PermissionError("rate exhausted"))
    monkeypatch.setattr(module, "enforce_ingestion_write_rate_limit", rate)
    commands = PortfolioSourceObservationCommands(authority, lambda stage: service, reader)
    if status == "completed" and completed_at is not None:
        assert await commands.submit(submission) is job
    else:
        with pytest.raises(ObservationConflict, match="RECEIPT_NOT_COMPLETED"):
            await commands.submit(submission)
    service.get_job.assert_awaited_once_with("existing", tenant_id="tenant-synthetic")
    assert reader.find_matching_job.call_args.kwargs["tenant_id"] == "tenant-synthetic"
    service.assert_ingestion_writable.assert_not_awaited()
    service.create_or_get_job.assert_not_awaited()
    rate.assert_not_called()


async def test_unadmitted_producer_cannot_read_matching_receipt():
    submission, _ = _submission()
    reader = _reader()
    with pytest.raises(ObservationConflict, match="PRODUCER_NOT_ADMITTED"):
        await PortfolioSourceObservationCommands(
            UnqualifiedProducerAuthority(), Mock(), reader
        ).submit(submission)
    reader.find_matching_job.assert_not_awaited()


@pytest.mark.parametrize("blocked_control", ["mode", "rate"])
async def test_no_matching_fingerprint_still_requires_write_controls(monkeypatch, blocked_control):
    submission, fact = _submission()
    authority = UnqualifiedProducerAuthority(
        (
            ProducerSubmissionGrant(
                "tenant-synthetic", "portfolio-synthetic", "producer-synthetic", fact.family
            ),
        )
    )
    service = SimpleNamespace(
        assert_ingestion_writable=AsyncMock(
            side_effect=PermissionError("read-only") if blocked_control == "mode" else None
        ),
        create_or_get_job=AsyncMock(),
    )
    reader = _reader()
    rate = Mock(side_effect=PermissionError("rate exhausted"))
    monkeypatch.setattr(module, "enforce_ingestion_write_rate_limit", rate)
    expected = "MODE_BLOCKS_WRITES" if blocked_control == "mode" else "RATE_LIMIT_EXCEEDED"
    with pytest.raises(ObservationConflict, match=expected):
        await PortfolioSourceObservationCommands(authority, lambda stage: service, reader).submit(
            submission
        )
    reader.find_matching_job.assert_awaited_once()
    service.create_or_get_job.assert_not_awaited()


async def test_dependency_wires_existing_fingerprint_reader():
    from src.services.ingestion_service.app.dependencies import (
        get_portfolio_source_observation_commands,
    )

    reader = _reader()
    commands = get_portfolio_source_observation_commands(
        authority=UnqualifiedProducerAuthority(), idempotency_replay_reader=reader
    )
    assert commands.idempotency_replay_reader is reader
