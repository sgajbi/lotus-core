"""Execute one frozen corporate-action release member under a fenced lease."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from ..domain import BookedTransaction
from ..ports.corporate_action_event_graph import CorporateActionEventGraphUnitOfWorkFactory
from .commands import ProcessTransactionCommand, TransactionEventMetadata
from .corporate_action_release import (
    ClaimedCorporateActionExecutionRelease,
    CorporateActionExecutionLeaseRequest,
    CorporateActionReleaseProgressOutcome,
)
from .errors import TransactionProcessingError
from .process_transaction import ProcessTransactionUseCase
from .results import ProcessTransactionResult, TransactionProcessingStatus


class CorporateActionReleaseWorkerStatus(StrEnum):
    """Classify one bounded poll without hiding durable terminal failure."""

    IDLE = "IDLE"
    ADVANCED = "ADVANCED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class CorporateActionReleaseWorkerResult:
    """Return one poll's exact release and member outcome."""

    status: CorporateActionReleaseWorkerStatus
    release_id: int | None = None
    execution_ordinal: int | None = None
    transaction_id: str | None = None
    transaction_status: TransactionProcessingStatus | None = None


class ProcessNextCorporateActionReleaseUseCase:
    """Claim, authenticate, process, and fence one exact ordered member."""

    def __init__(
        self,
        *,
        unit_of_work_factory: CorporateActionEventGraphUnitOfWorkFactory,
        process_transaction: ProcessTransactionUseCase,
        lease_owner: str,
        lease_duration_seconds: int = 60,
        token_factory: Callable[[], str] = lambda: secrets.token_hex(32),
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._process_transaction = process_transaction
        self._lease_owner = lease_owner
        self._lease_duration_seconds = lease_duration_seconds
        self._token_factory = token_factory

    async def execute(self) -> CorporateActionReleaseWorkerResult:
        lease = CorporateActionExecutionLeaseRequest(
            owner=self._lease_owner,
            token=self._token_factory(),
            duration_seconds=self._lease_duration_seconds,
        )
        claim = await self._claim(lease)
        if claim is None:
            return CorporateActionReleaseWorkerResult(CorporateActionReleaseWorkerStatus.IDLE)
        transaction = await self._load_owned_transaction(claim)
        try:
            processing = await self._process_with_heartbeat(
                claim,
                lease,
                ProcessTransactionCommand(
                    transaction=transaction,
                    metadata=TransactionEventMetadata(
                        event_id=(
                            "corporate-action-release:"
                            f"{claim.release_authority_hash}:"
                            f"{claim.next_member.execution_ordinal}"
                        ),
                        event_type="corporate_action.release.member",
                        schema_version="1.0.0",
                    ),
                ),
            )
        except TransactionProcessingError as exc:
            if exc.retryable:
                raise
            await self._fail(claim, exc.reason_code)
            return _worker_result(
                CorporateActionReleaseWorkerStatus.FAILED,
                claim,
            )
        progress = await self._advance(claim)
        if progress is CorporateActionReleaseProgressOutcome.LOST_OWNERSHIP:
            raise TransactionProcessingError(
                reason_code="corporate_action_release_lease_lost",
                detail={"release_id": claim.release_id},
                retryable=True,
            )
        return _worker_result(
            (
                CorporateActionReleaseWorkerStatus.COMPLETE
                if progress is CorporateActionReleaseProgressOutcome.COMPLETE
                else CorporateActionReleaseWorkerStatus.ADVANCED
            ),
            claim,
            transaction_status=processing.status,
        )

    async def _process_with_heartbeat(
        self,
        claim: ClaimedCorporateActionExecutionRelease,
        lease: CorporateActionExecutionLeaseRequest,
        command: ProcessTransactionCommand,
    ) -> ProcessTransactionResult:
        stop_heartbeat = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._renew_while_processing(claim, lease, stop_heartbeat),
            name=f"corporate-action-release-heartbeat:{claim.release_id}",
        )
        try:
            return await self._process_transaction.execute(command)
        finally:
            stop_heartbeat.set()
            await heartbeat

    async def _renew_while_processing(
        self,
        claim: ClaimedCorporateActionExecutionRelease,
        lease: CorporateActionExecutionLeaseRequest,
        stop: asyncio.Event,
    ) -> None:
        interval_seconds = max(1.0, lease.duration_seconds / 3)
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
                return
            except TimeoutError:
                pass
            async with self._unit_of_work_factory() as unit_of_work:
                renewed = await unit_of_work.releases.renew_lease(
                    release_id=claim.release_id,
                    lease=lease,
                    fence_token=claim.fence_token,
                )
                if not renewed:
                    raise TransactionProcessingError(
                        reason_code="corporate_action_release_lease_lost",
                        detail={"release_id": claim.release_id},
                        retryable=True,
                    )
                await unit_of_work.commit()

    async def _claim(
        self,
        lease: CorporateActionExecutionLeaseRequest,
    ) -> ClaimedCorporateActionExecutionRelease | None:
        async with self._unit_of_work_factory() as unit_of_work:
            claim = await unit_of_work.releases.claim_next(lease)
            await unit_of_work.commit()
        return claim

    async def _load_owned_transaction(
        self,
        claim: ClaimedCorporateActionExecutionRelease,
    ) -> BookedTransaction:
        async with self._unit_of_work_factory() as unit_of_work:
            transaction = await unit_of_work.releases.load_owned_transaction(claim)
            await unit_of_work.commit()
        return transaction

    async def _advance(
        self,
        claim: ClaimedCorporateActionExecutionRelease,
    ) -> CorporateActionReleaseProgressOutcome:
        async with self._unit_of_work_factory() as unit_of_work:
            outcome = await unit_of_work.releases.advance_member(
                release_id=claim.release_id,
                expected_ordinal=claim.next_member.execution_ordinal,
                lease_token=claim.lease_token,
                fence_token=claim.fence_token,
            )
            await unit_of_work.commit()
        return outcome

    async def _fail(
        self,
        claim: ClaimedCorporateActionExecutionRelease,
        reason_code: str,
    ) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            failed = await unit_of_work.releases.fail_release(
                release_id=claim.release_id,
                expected_ordinal=claim.next_member.execution_ordinal,
                lease_token=claim.lease_token,
                fence_token=claim.fence_token,
                terminal_reason=f"transaction_processing:{reason_code}"[:512],
            )
            if not failed:
                raise TransactionProcessingError(
                    reason_code="corporate_action_release_lease_lost",
                    detail={"release_id": claim.release_id},
                    retryable=True,
                )
            await unit_of_work.commit()


def _worker_result(
    status: CorporateActionReleaseWorkerStatus,
    claim: ClaimedCorporateActionExecutionRelease,
    *,
    transaction_status: TransactionProcessingStatus | None = None,
) -> CorporateActionReleaseWorkerResult:
    return CorporateActionReleaseWorkerResult(
        status=status,
        release_id=claim.release_id,
        execution_ordinal=claim.next_member.execution_ordinal,
        transaction_id=claim.next_member.transaction_id,
        transaction_status=transaction_status,
    )
