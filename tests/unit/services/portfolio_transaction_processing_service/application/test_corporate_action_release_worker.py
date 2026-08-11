"""Specify fenced ordered corporate-action release processing."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    ClaimedCorporateActionExecutionRelease,
    CorporateActionExecutionMemberAuthority,
    CorporateActionExecutionPayloadAuthorityError,
    CorporateActionReleaseProgressOutcome,
    CorporateActionReleaseWorkerStatus,
    ProcessNextCorporateActionReleaseUseCase,
    ProcessTransactionResult,
    TransactionProcessingError,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction

NOW = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)


def _transaction() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="CA-OUT-001",
        portfolio_id="PB-CA-001",
        instrument_id="INST-OLD",
        security_id="SEC-OLD",
        transaction_date=NOW,
        transaction_type="SPIN_OFF",
        quantity=Decimal("10"),
        price=Decimal("12.50"),
        gross_transaction_amount=Decimal("125.00"),
        trade_currency="SGD",
        currency="SGD",
        economic_event_id="CA-EVENT-001",
        linked_transaction_group_id="CA-GROUP-001",
        parent_event_reference="CA-PARENT-001",
        child_role="SOURCE_POSITION_CLOSE",
        epoch=3,
    )


def _claim() -> ClaimedCorporateActionExecutionRelease:
    return ClaimedCorporateActionExecutionRelease(
        release_id=41,
        release_authority_hash="a" * 64,
        member_count=1,
        next_member=CorporateActionExecutionMemberAuthority(
            execution_ordinal=0,
            transaction_id="CA-OUT-001",
            observation_id=91,
            transaction_epoch=3,
            observed_child_content_hash="b" * 64,
            transaction_payload_fingerprint="sha256:" + "c" * 64,
        ),
        attempt_count=1,
        fence_token=7,
        lease_owner="worker-1",
        lease_token="d" * 64,
        lease_expires_at=NOW + timedelta(seconds=60),
    )


class _Releases:
    def __init__(
        self,
        *,
        claim=None,
        progress=CorporateActionReleaseProgressOutcome.COMPLETE,
        next_claims=(),
        load_error: Exception | None = None,
        renew_result: bool = True,
        advance_error: Exception | None = None,
    ):
        self.claim = claim
        self.progress = list(progress) if isinstance(progress, (list, tuple)) else [progress]
        self.next_claims = list(next_claims)
        self.load_error = load_error
        self.renew_result = renew_result
        self.advance_error = advance_error
        self.claim_calls = 0
        self.advance_calls = []
        self.fail_calls = []

    async def claim_next(self, _lease):
        self.claim_calls += 1
        return self.claim

    async def load_owned_transaction(self, _claim):
        if self.load_error is not None:
            raise self.load_error
        return _transaction()

    async def advance_member(self, **kwargs):
        self.advance_calls.append(kwargs)
        if self.advance_error is not None:
            raise self.advance_error
        return self.progress.pop(0)

    async def load_owned_next(self, **_kwargs):
        return self.next_claims.pop(0) if self.next_claims else None

    async def renew_lease(self, **_kwargs):
        return self.renew_result

    async def fail_release(self, **kwargs):
        self.fail_calls.append(kwargs)
        return True


class _UnitOfWork:
    def __init__(self, releases: _Releases) -> None:
        self.releases = releases
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def commit(self):
        self.committed = True


def _worker(
    releases: _Releases,
    process: AsyncMock,
    *,
    lease_duration_seconds: int = 60,
    observer=None,
):
    units = []

    def factory():
        unit = _UnitOfWork(releases)
        units.append(unit)
        return unit

    return (
        ProcessNextCorporateActionReleaseUseCase(  # type: ignore[arg-type]
            unit_of_work_factory=factory,
            process_transaction=process,
            lease_owner="worker-1",
            lease_duration_seconds=lease_duration_seconds,
            token_factory=lambda: "d" * 64,
            **({"observer": observer} if observer is not None else {}),
        ),
        units,
    )


@pytest.mark.asyncio
async def test_idle_poll_does_not_open_financial_processing() -> None:
    process = AsyncMock()
    worker, units = _worker(_Releases(), process)

    result = await worker.execute()

    assert result.status is CorporateActionReleaseWorkerStatus.IDLE
    process.execute.assert_not_awaited()
    assert len(units) == 1 and units[0].committed


@pytest.mark.asyncio
async def test_worker_commits_claim_and_load_before_exact_member_processing() -> None:
    process = AsyncMock()
    process.execute.return_value = ProcessTransactionResult(
        status=TransactionProcessingStatus.PROCESSED,
        input_transaction_id="CA-OUT-001",
    )
    releases = _Releases(claim=_claim())
    worker, units = _worker(releases, process)

    result = await worker.execute()

    assert result.status is CorporateActionReleaseWorkerStatus.COMPLETE
    assert result.transaction_status is TransactionProcessingStatus.PROCESSED
    command = process.execute.await_args.args[0]
    assert command.metadata.event_id == f"corporate-action-release:{'a' * 64}:0"
    assert command.transaction.transaction_id == "CA-OUT-001"
    assert len(units) == 3 and all(unit.committed for unit in units)
    assert releases.advance_calls[0]["fence_token"] == 7
    assert result.processed_member_count == 1


@pytest.mark.asyncio
async def test_worker_drains_every_member_under_one_lease_without_reclaim() -> None:
    process = AsyncMock()
    process.execute.return_value = ProcessTransactionResult(
        status=TransactionProcessingStatus.PROCESSED,
        input_transaction_id="CA-OUT-001",
    )
    first = replace(
        _claim(),
        member_count=2,
    )
    second = replace(
        first,
        next_member=replace(
            first.next_member,
            execution_ordinal=1,
            transaction_id="CA-IN-001",
        ),
    )
    releases = _Releases(
        claim=first,
        progress=[
            CorporateActionReleaseProgressOutcome.ADVANCED,
            CorporateActionReleaseProgressOutcome.COMPLETE,
        ],
        next_claims=[second],
    )
    worker, units = _worker(releases, process)

    result = await worker.execute()

    assert result.status is CorporateActionReleaseWorkerStatus.COMPLETE
    assert result.execution_ordinal == 1
    assert result.processed_member_count == 2
    assert releases.claim_calls == 1
    assert [call["expected_ordinal"] for call in releases.advance_calls] == [0, 1]
    assert len(units) == 6 and all(unit.committed for unit in units)


@pytest.mark.asyncio
async def test_payload_authority_drift_fails_release_durably() -> None:
    process = AsyncMock()
    releases = _Releases(
        claim=_claim(),
        load_error=CorporateActionExecutionPayloadAuthorityError("payload changed"),
    )
    worker, units = _worker(releases, process)

    result = await worker.execute()

    assert result.status is CorporateActionReleaseWorkerStatus.FAILED
    assert result.processed_member_count == 0
    process.execute.assert_not_awaited()
    assert releases.fail_calls[0]["terminal_reason"] == (
        "transaction_processing:payload_authority_conflict"
    )
    assert units[-1].committed


@pytest.mark.asyncio
async def test_retryable_processing_failure_preserves_pending_progress() -> None:
    process = AsyncMock()
    process.execute.side_effect = TransactionProcessingError(
        reason_code="database_unavailable",
        detail={},
        retryable=True,
    )
    releases = _Releases(claim=_claim())
    worker, _units = _worker(releases, process)

    with pytest.raises(TransactionProcessingError, match="{}"):
        await worker.execute()

    assert releases.advance_calls == []
    assert releases.fail_calls == []


@pytest.mark.asyncio
async def test_terminal_processing_failure_is_durably_failed_under_fence() -> None:
    process = AsyncMock()
    process.execute.side_effect = TransactionProcessingError(
        reason_code="invalid_financial_effect",
        detail={},
        retryable=False,
    )
    releases = _Releases(claim=_claim())
    worker, units = _worker(releases, process)

    result = await worker.execute()

    assert result.status is CorporateActionReleaseWorkerStatus.FAILED
    assert releases.advance_calls == []
    assert releases.fail_calls[0]["terminal_reason"] == (
        "transaction_processing:invalid_financial_effect"
    )
    assert units[-1].committed


@pytest.mark.asyncio
async def test_lost_progress_fence_is_retryable_and_never_claimed_complete() -> None:
    process = AsyncMock()
    process.execute.return_value = ProcessTransactionResult(
        status=TransactionProcessingStatus.DUPLICATE,
        input_transaction_id="CA-OUT-001",
    )
    releases = _Releases(
        claim=_claim(),
        progress=CorporateActionReleaseProgressOutcome.LOST_OWNERSHIP,
    )
    worker, _units = _worker(releases, process)

    with pytest.raises(TransactionProcessingError) as raised:
        await worker.execute()

    assert raised.value.retryable
    assert raised.value.reason_code == "corporate_action_release_lease_lost"


@pytest.mark.asyncio
async def test_heartbeat_lease_loss_cancels_slow_processing_before_progress() -> None:
    processing_cancelled = asyncio.Event()
    process = AsyncMock()

    async def slow_processing(_command):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            processing_cancelled.set()
            raise

    process.execute.side_effect = slow_processing
    releases = _Releases(claim=_claim(), renew_result=False)
    observer = MagicMock()
    worker, _units = _worker(
        releases,
        process,
        lease_duration_seconds=1,
        observer=observer,
    )

    with pytest.raises(TransactionProcessingError) as raised:
        await asyncio.wait_for(worker.execute(), timeout=2)

    assert raised.value.reason_code == "corporate_action_release_lease_lost"
    assert raised.value.retryable
    assert processing_cancelled.is_set()
    assert releases.advance_calls == []
    assert releases.fail_calls == []
    observer.observe_lease_renewal.assert_called_once()
    assert observer.observe_lease_renewal.call_args.args[0].value == "lost"
