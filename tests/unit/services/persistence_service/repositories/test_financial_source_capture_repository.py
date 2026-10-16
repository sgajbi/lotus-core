"""Verified immutable cache bytes and currency fencing; mocked SQL earns no financial proof."""

import hashlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.portfolio_financial_source_cuts import InputRole
from portfolio_common.portfolio_financial_source_cut_models import (
    FinancialSourceCaptureRow,
    FinancialSourceCaptureSegmentRow,
)

from src.services.persistence_service.app.ports.financial_source_captures import (
    SourceCaptureRequest,
    SourceCaptureUnavailable,
)
from src.services.persistence_service.app.repositories.financial_source_capture_repository import (
    FinancialSourceCaptureRepository,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def cache(
    *,
    currency="USD",
    changed=False,
    gap=False,
    incomplete=False,
    missing=False,
    streamed_count=1,
    context_changes=None,
    byte_count=None,
):
    raw = b'{"unit-control":"opaque acquired bytes"}'
    request = SourceCaptureRequest(
        "tenant",
        "portfolio",
        InputRole.CASH,
        "PortfolioFinancialSourceObservations",
        "v1",
        b"{}",
        "a" * 64,
        "b" * 64,
        "receipt",
        "1",
        None,
        currency="USD",
    )
    context = dict(
        snapshot_epoch=None,
        request_scope=None,
        returned_count=1,
        total_count=1,
        next_page_token=None,
        completed_receipt_id="receipt",
        captured_at=datetime(2026, 10, 16, tzinfo=UTC).isoformat(),
        schema_version="v1",
        export_job_id=None,
        refresh_of_job_id=None,
        currency=currency,
    )
    context.update(context_changes or {})
    header = FinancialSourceCaptureRow(
        tenant_id="tenant",
        capture_id=request.capture_id,
        source_product=request.product_name,
        product_version="v1",
        selector_hash=request.selector_hash,
        typed_content_hash=request.expected_content_hash,
        raw_hash=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw) if byte_count is None else byte_count,
        segment_count=1,
        serializer_id="portfolio-cash-availability:domain-json:v1",
        mime_type="application/json",
        source_context=context,
    )

    async def segments():
        for index in range(streamed_count):
            yield FinancialSourceCaptureSegmentRow(
                tenant_id="tenant",
                capture_id=request.capture_id,
                segment_index=index + 1 if gap else index,
                raw_bytes=raw + b" " if changed else raw,
            )

    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[None if missing else header, 0 if incomplete else 1]),
        stream_scalars=AsyncMock(return_value=segments()),
    )

    @asynccontextmanager
    async def sessions():
        yield session

    return FinancialSourceCaptureRepository(sessions), request


async def test_complete_cached_artifact_returns_original_context_and_verified_owned_bytes():
    repository, request = cache()
    page = await repository.cached_capture(request)
    try:
        assert page.retained_bytes_verified is True
        assert page.captured_at == datetime(2026, 10, 16, tzinfo=UTC)
        assert page.snapshot_epoch is page.request_scope is None
        assert b"opaque acquired bytes" in b"".join(page.capture_bytes.segments())
    finally:
        page.capture_bytes.close()


@pytest.mark.parametrize("kwargs", [{"changed": True}, {"gap": True}, {"currency": "SGD"}])
async def test_raw_gap_or_currency_drift_cannot_bypass_original_source_validation(kwargs):
    repository, request = cache(**kwargs)
    with pytest.raises(SourceCaptureUnavailable):
        await repository.cached_capture(request)


async def test_partial_persisted_segments_are_reacquired_not_declared_complete():
    repository, request = cache(incomplete=True)
    assert await repository.cached_capture(request) is None


async def test_absent_cache_returns_no_artifact_without_reading_segments():
    repository, request = cache(missing=True)
    assert await repository.cached_capture(request) is None


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"streamed_count": 0}, "SEGMENT_COUNT"),
        ({"streamed_count": 2}, "SEGMENT_COUNT"),
        ({"byte_count": 999}, "RAW_DRIFT"),
        ({"context_changes": {"returned_count": 2}}, "COUNT"),
        ({"context_changes": {"captured_at": "invalid"}}, "isoformat"),
    ],
)
async def test_cached_count_or_context_failure_retires_acquired_spool(kwargs, code, monkeypatch):
    from src.services.persistence_service.app.ports import financial_source_captures as port

    streams = []
    original = port.tempfile.SpooledTemporaryFile

    def tracked_spool(*args, **options):
        stream = original(*args, **options)
        streams.append(stream)
        return stream

    monkeypatch.setattr(port.tempfile, "SpooledTemporaryFile", tracked_spool)
    repository, request = cache(**kwargs)
    with pytest.raises((SourceCaptureUnavailable, ValueError), match=code):
        await repository.cached_capture(request)
    assert len(streams) == 1 and streams[0].closed


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("typed", "DIVERGENT_REPLAY"),
        ("raw", "DIVERGENT_REPLAY"),
        ("epoch", "DIVERGENT_REPLAY"),
        ("scope", "DIVERGENT_REPLAY"),
        ("currency", "CACHED_CURRENCY_MISMATCH"),
        ("gap", "SEGMENT_GAP"),
        ("excess", "SEGMENT_GAP"),
    ],
)
async def test_append_refuses_divergent_or_discontinuous_replay_without_link(mutation, code):
    repository, request = cache()
    page = await repository.cached_capture(request)
    existing = SimpleNamespace(
        typed_content_hash=page.typed_content_hash,
        raw_hash=page.raw_hash,
        source_context=dict(
            snapshot_epoch=page.snapshot_epoch, request_scope=page.request_scope, currency="USD"
        ),
    )
    if mutation == "typed":
        existing.typed_content_hash = "c" * 64
    elif mutation == "raw":
        existing.raw_hash = "c" * 64
    elif mutation in {"epoch", "scope", "currency"}:
        existing.source_context[
            {"epoch": "snapshot_epoch", "scope": "request_scope", "currency": "currency"}[mutation]
        ] = "different"
    count = MagicMock()
    count.one.return_value = (1, 1, 1) if mutation == "gap" else (2, 0, 1)
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=existing),
        execute=AsyncMock(return_value=count),
        add=MagicMock(),
        flush=AsyncMock(),
    )
    try:
        with pytest.raises(SourceCaptureUnavailable, match=code):
            await repository.append(session, SimpleNamespace(tenant_id="tenant"), page)
        session.add.assert_not_called()
        session.flush.assert_not_awaited()
        assert session.execute.await_count == int(mutation in {"gap", "excess"})
    finally:
        page.capture_bytes.close()
