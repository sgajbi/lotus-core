"""Actual claim invariants and compiled conditional write fence, without PostgreSQL claims."""

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import InputRole
from portfolio_common.portfolio_financial_source_cut_models import (
    FinancialSourceCaptureLinkRow,
    FinancialSourceCaptureRow,
)
from sqlalchemy.dialects.postgresql import dialect

from src.services.persistence_service.app.ports.financial_source_captures import (
    CapturedSourcePage,
    SourceCaptureBytes,
    SourceCaptureRequest,
    SourceCaptureUnavailable,
)
from src.services.persistence_service.app.ports.financial_source_cut_work import (
    SourceCutClaim,
    SourceManifestRejected,
    StaleSourceCutClaim,
)
from src.services.persistence_service.app.repositories.financial_source_cut_work_repository import (
    FinancialSourceCutWorkRepository,
    claim_scope_hash,
    require_claim,
)

pytestmark = pytest.mark.unit


def claim_state():
    now = datetime(2026, 10, 16, tzinfo=UTC)
    checkpoint = {"role_index": 0, "page_index": 0}
    row = SimpleNamespace(
        work_id="work",
        tenant_id="tenant",
        product_name="PortfolioFinancialSourceCut",
        source_system="producer",
        registry_scope_id="registry",
        source_cut_id="cut",
        revision=1,
        partition_index=0,
        content_hash="a" * 64,
        lease_token="token",
        lease_expires_at=now + timedelta(seconds=30),
        status="CLAIMED",
        checkpoint=checkpoint,
    )
    claim = SourceCutClaim(
        "work",
        "tenant",
        "a" * 64,
        "token",
        now + timedelta(seconds=30),
        canonical_content_hash(checkpoint),
        claim_scope_hash(row),
    )
    return claim, row, now


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": "foreign"},
        {"lease_token": "replacement"},
        {"content_hash": "b" * 64},
        {"status": "COMPLETED"},
        {"checkpoint": {"role_index": 1}},
        {"partition_index": 1},
        {"registry_scope_id": "other-registry"},
        {"revision": 2},
        {"lease_expires_at": datetime(2026, 10, 16, tzinfo=UTC)},
    ],
)
def test_changed_tenant_root_token_checkpoint_status_or_expiry_refuses(changes):
    claim, row, now = claim_state()
    row.__dict__.update(changes)
    with pytest.raises(StaleSourceCutClaim):
        require_claim(row, claim, now)


def test_live_exact_claim_uses_supplied_db_time_and_exact_expiry_boundary():
    claim, row, now = claim_state()
    require_claim(row, claim, now)
    with pytest.raises(StaleSourceCutClaim):
        require_claim(row, claim, claim.lease_expires_at)


@pytest.mark.asyncio
async def test_terminal_conditional_write_contains_db_clock_and_exact_scope_and_refuses_zero_rows():
    claim, row, _ = claim_state()
    session = SimpleNamespace(execute=AsyncMock(return_value=MagicMock()))
    session.execute.return_value.scalar_one_or_none.return_value = None
    repository = FinancialSourceCutWorkRepository(lambda: None)
    with pytest.raises(StaleSourceCutClaim, match="EXPIRED_BEFORE_COMMIT"):
        await repository._release(session, row, claim, row.checkpoint, status="COMPLETED")
    statement = session.execute.call_args.args[0]
    compiled = statement.compile(dialect=dialect())
    sql = str(compiled)
    assert "lease_expires_at > clock_timestamp()" in sql
    assert "tenant_id =" in sql and "lease_token =" in sql and "content_hash =" in sql
    assert "RETURNING" in sql
    assert {"tenant", "token", "a" * 64, "work", "COMPLETED"} <= set(
        value for value in compiled.params.values() if isinstance(value, str)
    )
    session.execute.return_value.scalar_one_or_none.return_value = "work"
    await repository._release(session, row, claim, row.checkpoint, status="COMPLETED")


@pytest.mark.asyncio
async def test_capture_writes_at_most_two_segments_and_requires_retained_whole_byte_verification():
    _, work, now = claim_state()
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

    async def chunks():
        for _ in range(5):
            yield b"a" * 524288

    owned = await SourceCaptureBytes.acquire(chunks())
    page = CapturedSourcePage(
        request,
        owned,
        "portfolio-cash-availability:domain-json:v1",
        "application/json",
        "b" * 64,
        None,
        None,
        1,
        1,
        None,
        "receipt",
        now,
        "v1",
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None), flush=AsyncMock(), add=MagicMock(), execute=AsyncMock()
    )
    count_result = MagicMock()
    count_result.one.return_value = (0, None, None)
    session.execute.return_value = count_result
    repository = FinancialSourceCutWorkRepository(lambda: None)
    try:
        assert await repository._append_capture(session, work, page) is False
        inserts = [call.args[0] for call in session.execute.call_args_list[1:]]
        assert len(inserts) == 2
        assert (
            sum(
                len(statement.compile(dialect=dialect()).params["raw_bytes"])
                for statement in inserts
            )
            == 1048576
        )
        assert not any(
            isinstance(call.args[0], FinancialSourceCaptureLinkRow)
            for call in session.add.call_args_list
        )
        header = next(
            call.args[0]
            for call in session.add.call_args_list
            if isinstance(call.args[0], FinancialSourceCaptureRow)
        )
        session.scalar.return_value = header
        session.execute.reset_mock()
        count_result.one.return_value = (5, 0, 4)
        assert await repository._append_capture(session, work, page) is False
        session.add.reset_mock()
        assert (
            await repository._append_capture(
                session, work, replace(page, retained_bytes_verified=True)
            )
            is True
        )
        assert isinstance(session.add.call_args.args[0], FinancialSourceCaptureLinkRow)
    finally:
        owned.close()


@pytest.mark.asyncio
async def test_actual_claim_uses_context_manager_factory_and_database_time_for_fresh_token():
    _, row, now = claim_state()
    row.status, row.attempts = "PENDING", 0
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[now, "tenant", row, now]))

    @asynccontextmanager
    async def transaction():
        yield

    @asynccontextmanager
    async def sessions():
        yield session

    session.begin = transaction
    claim = await FinancialSourceCutWorkRepository(sessions).claim()
    assert claim.tenant_id == "tenant" and claim.lease_token != "token"
    assert claim.lease_expires_at == now + timedelta(seconds=30)
    assert claim.scope_hash == claim_scope_hash(row) and row.attempts == 1
    claim_sql = str(session.scalar.call_args_list[2].args[0].compile(dialect=dialect()))
    assert "SKIP LOCKED" in claim_sql and "LIMIT" in claim_sql


@pytest.mark.asyncio
async def test_renewal_uses_database_clock_and_expired_conditional_write_refuses():
    claim, row, now = claim_state()
    session = SimpleNamespace(scalar=AsyncMock(return_value=now + timedelta(seconds=60)))
    repository = FinancialSourceCutWorkRepository(lambda: None)
    renewed = await repository._renew(session, row, claim)
    assert (
        renewed.lease_token == claim.lease_token
        and renewed.lease_expires_at > claim.lease_expires_at
    )
    sql = str(session.scalar.call_args.args[0].compile(dialect=dialect()))
    assert "lease_expires_at > clock_timestamp()" in sql and "RETURNING" in sql
    session.scalar.return_value = None
    with pytest.raises(StaleSourceCutClaim, match="BEFORE_RENEWAL"):
        await repository._renew(session, row, claim)


@pytest.mark.asyncio
async def test_invalid_defer_code_refuses_before_session_creation():
    sessions = MagicMock(side_effect=AssertionError("must not open database"))
    repository = FinancialSourceCutWorkRepository(sessions)
    with pytest.raises(ValueError, match="closed source work refusal code"):
        await repository.defer(claim_state()[0], "arbitrary diagnostic")
    sessions.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("large", [False, True])
async def test_verification_page_limits_rows_and_bytes_without_consuming_history(large):
    records = [
        SimpleNamespace(declaration={"payload": "a" * (600_000 if large else 1)})
        for _ in range(3 if large else 502)
    ]
    visited = []

    async def stream():
        for row in records:
            visited.append(row)
            yield row

    session = SimpleNamespace(stream_scalars=AsyncMock(return_value=stream()))
    statement = MagicMock()
    statement.limit.return_value.execution_options.return_value = statement
    page, more = await FinancialSourceCutWorkRepository(lambda: None)._bounded_rows(
        session, statement
    )
    assert more is True and len(page) == (1 if large else 500)
    assert len(visited) == len(page) + 1
    assert page == records[: len(page)]


@pytest.mark.asyncio
async def test_single_oversized_verification_row_is_refused_instead_of_skipped():
    async def stream():
        yield SimpleNamespace(declaration={"payload": "a" * 1_048_576})

    session = SimpleNamespace(stream_scalars=AsyncMock(return_value=stream()))
    statement = MagicMock()
    with pytest.raises(SourceManifestRejected, match="ROW_BYTE_BUDGET"):
        await FinancialSourceCutWorkRepository(lambda: None)._bounded_rows(session, statement)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation,code",
    [
        ("request", "REQUEST_SUBSTITUTION"),
        ("epoch", "MIXED_EPOCH_OR_SCOPE"),
        ("scope", "MIXED_EPOCH_OR_SCOPE"),
        ("total", "MIXED_EPOCH_OR_SCOPE"),
        ("incomplete", "INCOMPLETE_COVERAGE"),
        ("excess", "INCOMPLETE_COVERAGE"),
    ],
)
async def test_capture_page_refuses_substitution_before_append_or_checkpoint_release(
    mutation, code
):
    claim, row, now = claim_state()
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
        "previous",
        1,
        currency="USD",
    )

    async def chunks():
        yield b"{}"

    owned = await SourceCaptureBytes.acquire(chunks())
    page = CapturedSourcePage(
        request,
        owned,
        "opaque:v1",
        "application/json",
        "b" * 64,
        None,
        None,
        1,
        2,
        None,
        "receipt",
        now,
        "v1",
    )
    row.checkpoint = dict(
        stage="CAPTURE",
        page_index=1,
        received_rows=1,
        snapshot_epoch=None,
        request_scope=None,
        total_count=2,
    )
    checkpoint = dict(row.checkpoint)
    expected = request
    if mutation == "request":
        expected = replace(request, page_token="substituted")
    elif mutation in {"epoch", "scope", "total"}:
        row.checkpoint[
            {"epoch": "snapshot_epoch", "scope": "request_scope", "total": "total_count"}[mutation]
        ] = "foreign"
    elif mutation == "incomplete":
        row.checkpoint["received_rows"] = 0
    else:
        row.checkpoint["received_rows"] = 2
    checkpoint = dict(row.checkpoint)
    session = SimpleNamespace(flush=AsyncMock())

    @asynccontextmanager
    async def context():
        yield session

    session.begin = context
    repository = FinancialSourceCutWorkRepository(context)
    repository._locked = AsyncMock(return_value=row)
    repository._request = AsyncMock(return_value=expected)
    repository._append_capture = AsyncMock()
    repository._release = AsyncMock()
    try:
        with pytest.raises(SourceCaptureUnavailable, match=code):
            await repository._save_capture(claim, page)
        repository._append_capture.assert_not_awaited()
        repository._release.assert_not_awaited()
        session.flush.assert_not_awaited()
        assert row.checkpoint == checkpoint
    finally:
        owned.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("gap", [False, True])
async def test_partition_spawn_uses_chunk_order_and_preserves_bounded_checkpoint(gap):
    _, row, _ = claim_state()
    row.receipt_job_id = "receipt"
    result = MagicMock()
    result.all.return_value = [SimpleNamespace(chunk_index=1 if gap else 0)]
    session = SimpleNamespace(scalars=AsyncMock(return_value=result), add=MagicMock())
    checkpoint = {"stage": "SPAWN_CAPTURES", "spawned_chunks": 0}
    repository = FinancialSourceCutWorkRepository(lambda: None)
    if gap:
        with pytest.raises(SourceManifestRejected, match="PARTITION_GAP"):
            await repository._spawn_partitions(
                session, row, SimpleNamespace(chunk_count=1), checkpoint
            )
        assert checkpoint == {"stage": "SPAWN_CAPTURES", "spawned_chunks": 0}
        session.add.assert_not_called()
    else:
        actual = await repository._spawn_partitions(
            session, row, SimpleNamespace(chunk_count=1), checkpoint
        )
        assert actual == {"stage": "WAIT_CAPTURES", "spawned_chunks": 1}
        partition = session.add.call_args.args[0]
        assert partition.tenant_id == "tenant" and partition.partition_index == 1
        assert partition.receipt_job_id == "receipt" and partition.content_hash == row.content_hash
        assert partition.checkpoint == {
            "stage": "CAPTURE",
            "role_index": 0,
            "page_index": 0,
            "completed_inputs": 0,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("continuation,retained", [(True, True), (False, True), (False, False)])
async def test_capture_checkpoint_advances_only_after_verified_retained_link(
    continuation, retained
):
    claim, row, now = claim_state()
    request = SourceCaptureRequest(
        "tenant",
        "portfolio",
        InputRole.FLOWS,
        "PortfolioFinancialFlowObservations",
        "v1",
        b"{}",
        "a" * 64,
        "b" * 64,
        "receipt",
        "1",
        None,
        currency="USD",
    )

    async def chunks():
        yield b"{}"

    owned = await SourceCaptureBytes.acquire(chunks())
    page = CapturedSourcePage(
        request,
        owned,
        "opaque:v1",
        "application/json",
        "b" * 64,
        None,
        None,
        1,
        2 if continuation else 1,
        "next-page" if continuation else None,
        "receipt",
        now,
        "v1",
        retained_bytes_verified=retained,
    )
    row.checkpoint = {"stage": "CAPTURE", "role_index": 4, "page_index": 0, "completed_inputs": 2}
    original = dict(row.checkpoint)
    session = SimpleNamespace(flush=AsyncMock())

    @asynccontextmanager
    async def context():
        yield session

    session.begin = context
    repository = FinancialSourceCutWorkRepository(context)
    repository._locked = AsyncMock(return_value=row)
    repository._request = AsyncMock(return_value=request)
    repository._append_capture = AsyncMock(return_value=retained)
    repository._release = AsyncMock()
    repository._renew = AsyncMock(return_value=replace(claim, lease_token="renewed"))
    try:
        result = await repository._save_capture(claim, page)
        repository._append_capture.assert_awaited_once_with(session, row, page)
        assert row.checkpoint == original
        if not retained:
            assert result.lease_token == "renewed"
            repository._release.assert_not_awaited()
            repository._renew.assert_awaited_once_with(session, row, claim)
        else:
            assert result is None
            repository._renew.assert_not_awaited()
            saved = repository._release.await_args.args[3]
            if continuation:
                assert saved["page_index"] == 1 and saved["page_token"] == "next-page"
                assert saved["received_rows"] == 1 and saved["total_count"] == 2
                assert saved["role_index"] == 4 and saved["completed_inputs"] == 2
                assert "last_portfolio_id" not in saved
            else:
                assert saved["page_index"] == saved["role_index"] == saved["received_rows"] == 0
                assert saved["page_token"] is saved["total_count"] is None
                assert saved["last_portfolio_id"] == "portfolio" and saved["completed_inputs"] == 3
    finally:
        owned.close()
