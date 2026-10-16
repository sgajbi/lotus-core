"""Short DB-time lease transactions; immutable captures and terminal effects commit together."""

import json
from uuid import uuid4

from portfolio_common.config import KAFKA_PORTFOLIO_FINANCIAL_SOURCE_CUTS_COMPLETED_TOPIC
from portfolio_common.database_models import IngestionJob
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import (
    InputRole,
)
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.portfolio_financial_source_cut_admission import registry_member_from_payload
from portfolio_common.portfolio_financial_source_cut_events import (
    PortfolioFinancialSourceCutCompletedEvent,
)
from portfolio_common.portfolio_financial_source_cut_models import (
    FinancialSourceChunkRow,
    FinancialSourceCutRow,
    FinancialSourceCutWorkRow,
    FinancialSourceInputRow,
    HistoricalRegistryMemberRow,
)
from sqlalchemy import func, select, tuple_
from sqlalchemy.exc import IntegrityError

from ..application.financial_source_cut_processing import (
    verify_chunk_step,
    verify_input_page,
    verify_member_page,
)
from ..ports.financial_source_captures import (
    SourceCaptureRequest,
    SourceCaptureUnavailable,
)
from ..ports.financial_source_cut_work import (
    SourceCutProgress,
    SourceManifestRejected,
    StaleSourceCutClaim,
)
from .financial_source_capture_repository import FinancialSourceCaptureRepository
from .financial_source_cut_claims import (
    FinancialSourceCutClaims,
)
from .financial_source_cut_claims import (
    claim_scope_hash as claim_scope_hash,
)
from .financial_source_cut_claims import (
    manifest_from_row as manifest_from_row,
)
from .financial_source_cut_claims import (
    predicates as predicates,
)
from .financial_source_cut_claims import (
    require_claim as require_claim,
)
from .financial_source_cut_claims import (
    scope as scope,
)


class FinancialSourceCutWorkRepository:
    def __init__(self, session_factory, *, lease_seconds=30, retry_seconds=5):
        if not 10 <= lease_seconds <= 300 or not 1 <= retry_seconds <= 60:
            raise ValueError("bounded capture lease/backoff required")
        self._claims = FinancialSourceCutClaims(
            session_factory, lease_seconds=lease_seconds, retry_seconds=retry_seconds
        )
        self._captures = FinancialSourceCaptureRepository(session_factory)

    async def _request(self, session, row):
        if row.partition_index == 0:
            stage = row.checkpoint["stage"]
            if stage == "READY":
                return None
            return SourceCutProgress(stage)
        checkpoint = row.checkpoint
        query = select(FinancialSourceInputRow).where(
            *predicates(FinancialSourceInputRow, row),
            FinancialSourceInputRow.chunk_index == row.partition_index - 1,
        )
        if checkpoint.get("last_portfolio_id") is not None:
            query = query.where(
                FinancialSourceInputRow.portfolio_id > checkpoint["last_portfolio_id"]
            )
        source = await session.scalar(query.order_by(FinancialSourceInputRow.portfolio_id).limit(1))
        if source is None:
            return None
        selection = source.declaration["selections"][checkpoint.get("role_index", 0)]
        return SourceCaptureRequest(
            row.tenant_id,
            source.portfolio_id,
            InputRole(selection["role"]),
            selection["product_name"],
            selection["product_version"],
            json.dumps(selection["selector"], sort_keys=True, separators=(",", ":")).encode(),
            selection["selector_hash"],
            selection["content_hash"],
            selection["receipt_job_id"],
            selection["source_revision"],
            checkpoint.get("page_token"),
            checkpoint.get("page_index", 0),
            currency=source.declaration["currency"],
        )

    async def next_capture(self, claim):
        async with self.sessions() as session, session.begin():
            row = await self._locked(session, claim)
            return await self._request(session, row)

    async def _bounded_rows(self, session, statement):
        records: list[HistoricalRegistryMemberRow | FinancialSourceInputRow] = []
        size, more = 0, False
        async for record in await session.stream_scalars(
            statement.limit(501).execution_options(yield_per=1)
        ):
            length = len(
                json.dumps(record.declaration, separators=(",", ":"), ensure_ascii=False).encode()
            )
            if records and (len(records) == 500 or size + length > 1048576):
                more = True
                break
            if length > 1048576:
                raise SourceManifestRejected("SOURCE_VERIFICATION_ROW_BYTE_BUDGET")
            records.append(record)
            size += length
        return records, more

    async def _require_registry_mapping(self, session, row, record):
        registry = await session.scalar(
            select(FinancialSourceCutRow).where(
                FinancialSourceCutRow.tenant_id == row.tenant_id,
                FinancialSourceCutRow.product_name == "PortfolioHistoricalRegistry",
                FinancialSourceCutRow.source_system == row.source_system,
                FinancialSourceCutRow.registry_scope_id == row.registry_scope_id,
                FinancialSourceCutRow.content_hash == record.declaration["registry_root"],
            )
        )
        if registry is None:
            raise SourceManifestRejected("SOURCE_REGISTRY_ROOT_UNAVAILABLE")
        manifest_from_row(registry)
        status = await session.scalar(
            select(FinancialSourceCutWorkRow.status).where(
                *predicates(FinancialSourceCutWorkRow, registry),
                FinancialSourceCutWorkRow.partition_index == 0,
            )
        )
        if status == "FAILED":
            raise SourceManifestRejected("SOURCE_REGISTRY_CUSTODY_REJECTED")
        if status != "COMPLETED":
            raise SourceCaptureUnavailable("SOURCE_REGISTRY_CUSTODY_PENDING")
        matches = (
            await session.scalars(
                select(HistoricalRegistryMemberRow)
                .where(
                    *predicates(HistoricalRegistryMemberRow, registry),
                    HistoricalRegistryMemberRow.core_portfolio_id == record.portfolio_id,
                    HistoricalRegistryMemberRow.member_revision
                    == record.declaration["member_revision"],
                )
                .limit(2)
            )
        ).all()
        if len(matches) != 1:
            raise SourceManifestRejected("SOURCE_REGISTRY_MEMBER_MAPPING_AMBIGUOUS_OR_MISSING")
        member = registry_member_from_payload(matches[0].declaration)
        if member.content_hash != matches[0].content_hash:
            raise SourceManifestRejected("SOURCE_REGISTRY_MEMBER_TYPED_DRIFT")

    async def advance(self, claim, progress):
        async with self.sessions() as session, session.begin():
            row = await self._locked(session, claim)
            if row.partition_index != 0 or row.checkpoint["stage"] != progress.stage:
                raise StaleSourceCutClaim("SOURCE_WORK_STAGE_SUBSTITUTION")
            record = await session.scalar(
                select(FinancialSourceCutRow).where(*predicates(FinancialSourceCutRow, row))
            )
            manifest = manifest_from_row(record)
            checkpoint = dict(row.checkpoint)
            if progress.stage == "VERIFY_CHUNKS":
                state = checkpoint.get("ordered_root_checkpoint")
                next_index = 0 if state is None else state[1]
                chunk = await session.scalar(
                    select(FinancialSourceChunkRow).where(
                        *predicates(FinancialSourceChunkRow, row),
                        FinancialSourceChunkRow.chunk_index == next_index,
                    )
                )
                checkpoint = verify_chunk_step(checkpoint, manifest, chunk)
            elif progress.stage == "VERIFY_MEMBERS":
                statement = select(HistoricalRegistryMemberRow).where(
                    *predicates(HistoricalRegistryMemberRow, row)
                )
                if checkpoint.get("last_member_key") is not None:
                    statement = statement.where(
                        tuple_(
                            HistoricalRegistryMemberRow.provider_namespace,
                            HistoricalRegistryMemberRow.source_member_id,
                        )
                        > tuple(checkpoint["last_member_key"])
                    )
                records, more = await self._bounded_rows(
                    session,
                    statement.order_by(
                        HistoricalRegistryMemberRow.provider_namespace,
                        HistoricalRegistryMemberRow.source_member_id,
                    ),
                )
                checkpoint = verify_member_page(checkpoint, manifest, records, has_more=more)
            elif progress.stage == "VERIFY_INPUTS":
                statement = select(FinancialSourceInputRow).where(
                    *predicates(FinancialSourceInputRow, row)
                )
                if checkpoint.get("last_verified_portfolio_id") is not None:
                    statement = statement.where(
                        FinancialSourceInputRow.portfolio_id
                        > checkpoint["last_verified_portfolio_id"]
                    )
                records, more = await self._bounded_rows(
                    session, statement.order_by(FinancialSourceInputRow.portfolio_id)
                )
                for source in records:
                    await self._require_registry_mapping(session, row, source)
                checkpoint = verify_input_page(checkpoint, manifest, records, has_more=more)
            elif progress.stage == "SPAWN_CAPTURES":
                checkpoint = await self._spawn_partitions(session, row, manifest, checkpoint)
            elif progress.stage == "WAIT_CAPTURES":
                failed = await session.scalar(
                    select(FinancialSourceCutWorkRow.work_id)
                    .where(
                        *predicates(FinancialSourceCutWorkRow, row),
                        FinancialSourceCutWorkRow.partition_index > 0,
                        FinancialSourceCutWorkRow.status == "FAILED",
                    )
                    .limit(1)
                )
                if failed is not None:
                    raise SourceManifestRejected("SOURCE_CAPTURE_PARTITION_REJECTED")
                pending = await session.scalar(
                    select(func.count())
                    .select_from(FinancialSourceCutWorkRow)
                    .where(
                        *predicates(FinancialSourceCutWorkRow, row),
                        FinancialSourceCutWorkRow.partition_index > 0,
                        FinancialSourceCutWorkRow.status != "COMPLETED",
                    )
                )
                if pending == 0:
                    checkpoint["stage"] = "READY"
            await session.flush()
            await self._release(
                session,
                row,
                claim,
                checkpoint,
                error="SOURCE_CAPTURE_UNAVAILABLE"
                if checkpoint["stage"] == "WAIT_CAPTURES"
                else None,
            )

    async def _spawn_partitions(self, session, row, manifest, checkpoint):
        first = checkpoint.get("spawned_chunks", 0)
        chunks = (
            await session.scalars(
                select(FinancialSourceChunkRow)
                .where(
                    *predicates(FinancialSourceChunkRow, row),
                    FinancialSourceChunkRow.chunk_index >= first,
                )
                .order_by(FinancialSourceChunkRow.chunk_index)
                .limit(500)
            )
        ).all()
        for chunk in chunks:
            if chunk.chunk_index != checkpoint.get("spawned_chunks", 0):
                raise SourceManifestRejected("SOURCE_CAPTURE_PARTITION_GAP")
            session.add(
                FinancialSourceCutWorkRow(
                    work_id=str(uuid4()),
                    **scope(row),
                    partition_index=chunk.chunk_index + 1,
                    content_hash=row.content_hash,
                    receipt_job_id=row.receipt_job_id,
                    checkpoint={
                        "stage": "CAPTURE",
                        "role_index": 0,
                        "page_index": 0,
                        "completed_inputs": 0,
                    },
                )
            )
            checkpoint["spawned_chunks"] += 1
        if checkpoint["spawned_chunks"] == manifest.chunk_count:
            checkpoint["stage"] = "WAIT_CAPTURES"
        return checkpoint

    async def save_capture(self, claim, page):
        active_page = page
        try:
            while True:
                next_claim = await self._save_capture(claim, active_page)
                if next_claim is None:
                    return
                claim = next_claim
                verified = await self.cached_capture(page.request)
                if verified is not None:
                    if active_page is not page:
                        active_page.capture_bytes.close()
                    active_page = verified
        except IntegrityError as error:
            driver_error = error.orig.__cause__
            if (
                getattr(error.orig, "sqlstate", None) != "23505"
                or getattr(driver_error, "constraint_name", None)
                != "portfolio_financial_source_captures_pkey"
            ):
                raise
            # The failed transaction has rolled back. Retry reuses and verifies
            # the winning immutable bytes; unrelated SQL failures propagate.
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_CONCURRENT_REUSE") from error
        finally:
            if active_page is not page:
                active_page.capture_bytes.close()

    async def _save_capture(self, claim, page):
        async with self.sessions() as session, session.begin():
            row = await self._locked(session, claim)
            request = await self._request(session, row)
            if request != page.request:
                raise SourceCaptureUnavailable("SOURCE_CAPTURE_REQUEST_SUBSTITUTION")
            checkpoint = dict(row.checkpoint)
            seen = checkpoint.get("received_rows", 0)
            if checkpoint.get("page_index", 0) > 0 and (
                checkpoint.get("snapshot_epoch"),
                checkpoint.get("request_scope"),
                checkpoint.get("total_count"),
            ) != (page.snapshot_epoch, page.request_scope, page.total_count):
                raise SourceCaptureUnavailable("SOURCE_CAPTURE_MIXED_EPOCH_OR_SCOPE")
            if seen + page.returned_count > page.total_count or (
                page.next_page_token is None and seen + page.returned_count != page.total_count
            ):
                raise SourceCaptureUnavailable("SOURCE_CAPTURE_INCOMPLETE_COVERAGE")
            if not await self._append_capture(session, row, page):
                await session.flush()
                return await self._renew(session, row, claim)
            checkpoint.update(
                received_rows=seen + page.returned_count,
                total_count=page.total_count,
                snapshot_epoch=page.snapshot_epoch,
                request_scope=page.request_scope,
                page_token=page.next_page_token,
                page_index=request.page_index + 1,
            )
            if page.next_page_token is None:
                checkpoint.update(
                    role_index=checkpoint.get("role_index", 0) + 1,
                    page_index=0,
                    page_token=None,
                    received_rows=0,
                    total_count=None,
                    snapshot_epoch=None,
                    request_scope=None,
                )
                if checkpoint["role_index"] == 5:
                    checkpoint.update(
                        role_index=0,
                        last_portfolio_id=request.portfolio_id,
                        completed_inputs=checkpoint.get("completed_inputs", 0) + 1,
                    )
            await session.flush()
            await self._release(session, row, claim, checkpoint)

    async def complete(self, claim):
        async with self.sessions() as session, session.begin():
            row = await self._locked(session, claim)
            record = await session.scalar(
                select(FinancialSourceCutRow).where(*predicates(FinancialSourceCutRow, row))
            )
            manifest = manifest_from_row(record)
            if await self._request(session, row) is not None:
                raise SourceCaptureUnavailable("SOURCE_CUT_MANIFEST_INCOMPLETE")
            if row.partition_index > 0:
                chunk = await session.scalar(
                    select(FinancialSourceChunkRow).where(
                        *predicates(FinancialSourceChunkRow, row),
                        FinancialSourceChunkRow.chunk_index == row.partition_index - 1,
                    )
                )
                if chunk is None or row.checkpoint.get("completed_inputs", 0) != chunk.row_count:
                    raise SourceManifestRejected("SOURCE_CAPTURE_PARTITION_COUNT")
                await self._release(session, row, claim, row.checkpoint, status="COMPLETED")
                return
            if row.checkpoint["stage"] != "READY":
                raise SourceManifestRejected("SOURCE_MANIFEST_NOT_VERIFIED")
            if row.product_name == "PortfolioFinancialSourceCut":
                partitions, completed = (
                    await session.execute(
                        select(
                            func.count(),
                            func.count().filter(FinancialSourceCutWorkRow.status == "COMPLETED"),
                        ).where(
                            *predicates(FinancialSourceCutWorkRow, row),
                            FinancialSourceCutWorkRow.partition_index > 0,
                        )
                    )
                ).one()
                if partitions != manifest.chunk_count or completed != partitions:
                    raise SourceCaptureUnavailable("SOURCE_CAPTURE_PARTITIONS_PENDING")
            await self._complete_receipt(session, row, claim, record)

    async def _complete_receipt(self, session, row, claim, manifest):
        job = await session.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.tenant_id == row.tenant_id, IngestionJob.job_id == row.receipt_job_id
            )
            .with_for_update()
        )
        if job is None or job.status != "accepted" or job.completed_at is not None:
            raise SourceManifestRejected("SOURCE_CUT_RECEIPT_STATE_MISMATCH")
        now = await session.scalar(select(func.clock_timestamp()))
        event = PortfolioFinancialSourceCutCompletedEvent(
            **scope(row),
            content_hash=row.content_hash,
            predecessor_hash=manifest.declaration["predecessor_hash"],
            receipt_job_id=row.receipt_job_id,
            completed_at=now,
            compatibility_posture="DECLARED_UNVERIFIED"
            if row.checkpoint.get("compatibility_declaration_count", 0) > 0
            else "UNAVAILABLE",
        )
        aggregate = canonical_content_hash({k: v for k, v in scope(row).items() if k != "revision"})
        await OutboxRepository(session).create_outbox_event(
            aggregate_type="portfolio_financial_source_cut",
            aggregate_id=aggregate,
            partition_key=aggregate,
            event_type="PortfolioFinancialSourceCutCompleted",
            topic=KAFKA_PORTFOLIO_FINANCIAL_SOURCE_CUTS_COMPLETED_TOPIC,
            payload=event.model_dump(mode="json"),
            correlation_id=job.correlation_id,
        )
        job.status = "completed"
        job.completed_at = now
        await session.flush()
        await self._release(session, row, claim, row.checkpoint, status="COMPLETED")

    async def reject(self, claim):
        async with self.sessions() as session, session.begin():
            row = await self._locked(session, claim)
            job = await session.scalar(
                select(IngestionJob)
                .where(
                    IngestionJob.tenant_id == row.tenant_id,
                    IngestionJob.job_id == row.receipt_job_id,
                )
                .with_for_update()
            )
            if job is not None and job.status == "accepted":
                job.status = "failed"
                job.failure_reason = "Neutral source manifest did not reconcile"
            await session.flush()
            await self._release(
                session,
                row,
                claim,
                row.checkpoint,
                status="FAILED",
                error="SOURCE_MANIFEST_REJECTED",
            )

    async def defer(self, claim, error_code):
        if error_code != "SOURCE_CAPTURE_UNAVAILABLE":
            raise ValueError("closed source work refusal code required")
        async with self.sessions() as session, session.begin():
            row = await self._locked(session, claim)
            await self._release(session, row, claim, row.checkpoint, error=error_code)

    @property
    def sessions(self):
        return self._claims.sessions

    @sessions.setter
    def sessions(self, value):
        self._claims.sessions = value
        self._captures.sessions = value

    @property
    def lease_seconds(self):
        return self._claims.lease_seconds

    @lease_seconds.setter
    def lease_seconds(self, value):
        self._claims.lease_seconds = value

    @property
    def retry_seconds(self):
        return self._claims.retry_seconds

    @retry_seconds.setter
    def retry_seconds(self, value):
        self._claims.retry_seconds = value

    @property
    def last_tenant_id(self):
        return self._claims.last_tenant_id

    @last_tenant_id.setter
    def last_tenant_id(self, value):
        self._claims.last_tenant_id = value

    async def claim(self):
        return await self._claims.claim()

    async def _locked(self, session, claim):
        return await self._claims.locked(session, claim)

    async def _release(self, session, row, claim, checkpoint, *, status="PENDING", error=None):
        return await self._claims.release(
            session, row, claim, checkpoint, status=status, error=error
        )

    async def _renew(self, session, row, claim):
        return await self._claims.renew(session, row, claim)

    async def cached_capture(self, request):
        return await self._captures.cached_capture(request)

    async def _append_capture(self, session, row, page):
        return await self._captures.append(session, row, page)
