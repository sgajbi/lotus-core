"""Native receipt creation effect: immutable chunks, exact indexed reconciliation and seal work."""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from portfolio_common.database_models import Portfolio
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.portfolio_financial_source_cut_admission import (
    RegistryMemberInput,
    require_chunk_budget,
    require_exact_replay,
)
from portfolio_common.portfolio_financial_source_cut_models import (
    FinancialSourceChunkRow,
    FinancialSourceCutRow,
    FinancialSourceCutWorkRow,
    FinancialSourceHeadRow,
    FinancialSourceInputRow,
    HistoricalRegistryMemberRow,
)
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from ..domain.ingestion_job_lifecycle_policy import (
    IngestionJobTransition,
    ingestion_job_transition_allowed,
)
from ..DTOs.portfolio_financial_source_cut_dto import (
    FinancialChunkInput,
    FinancialSealInput,
    RegistryChunkInput,
    RegistrySealInput,
)


def command_kind(request):
    registry = isinstance(request, (RegistryChunkInput, RegistrySealInput))
    chunk = isinstance(request, (RegistryChunkInput, FinancialChunkInput))
    return ("PortfolioHistoricalRegistry" if registry else "PortfolioFinancialSourceCut", chunk)


def command_scope(request, tenant_id):
    product, _ = command_kind(request)
    return dict(
        tenant_id=tenant_id,
        product_name=product,
        source_system=request.source_system,
        registry_scope_id=request.registry_scope_id,
        source_cut_id=request.source_cut_id,
        revision=request.revision,
    )


def exact_scope(model, values):
    return [getattr(model, key) == value for key, value in values.items()]


def financial_input_hash(record):
    return canonical_content_hash(
        {
            "contract": "PortfolioFinancialSourceCutInput:v1",
            "selection": record.model_dump(mode="json"),
        }
    )


def require_custody_replay(existing_typed_hash, existing_raw_hash, *, typed_hash, raw_hash):
    try:
        require_exact_replay(
            existing_typed_hash, existing_raw_hash, typed_hash=typed_hash, raw_hash=raw_hash
        )
    except ValueError as error:
        raise ObservationConflict("SOURCE_CUT_DIVERGENT_REPLAY") from error


async def flush_unique_source_rows(session):
    try:
        await session.flush()
    except IntegrityError as error:
        driver = error.orig.__cause__
        if getattr(error.orig, "sqlstate", None) != "23505" or getattr(
            driver, "constraint_name", None
        ) not in {
            "portfolio_historical_registry_members_pkey",
            "portfolio_financial_source_cut_inputs_pkey",
        }:
            raise
        raise ObservationConflict("SOURCE_CHUNK_ORDER_OR_DUPLICATE") from error


@dataclass(frozen=True, slots=True)
class PortfolioFinancialSourceCutStager:
    request: RegistryChunkInput | RegistrySealInput | FinancialChunkInput | FinancialSealInput
    tenant_id: str
    raw_bytes: bytes
    received_at: datetime
    endpoint: str
    entity_type: str

    async def original_receipt(self, session_factory):
        """Read first immutable custody receipt; divergent raw replay never succeeds."""
        values = command_scope(self.request, self.tenant_id)
        chunk = isinstance(self.request, (RegistryChunkInput, FinancialChunkInput))
        model = FinancialSourceChunkRow if chunk else FinancialSourceCutRow
        statement = select(model).where(*exact_scope(model, values))
        if chunk:
            statement = statement.where(model.chunk_index == self.request.chunk_index)
        async with session_factory() as session:
            existing = await session.scalar(statement)
            if existing is None:
                return None
            typed_hash = (
                self.request.typed_content_hash
                if chunk
                else self.request.to_domain(self.tenant_id).content_hash
            )
            require_custody_replay(
                existing.typed_hash if chunk else existing.content_hash,
                existing.raw_hash,
                typed_hash=typed_hash,
                raw_hash=require_chunk_budget(self.raw_bytes, 1),
            )
            return existing.receipt_job_id

    async def stage(self, session, receipt):
        state = inspect(receipt)
        if (
            not session.in_transaction()
            or not state.persistent
            or state.session is not session.sync_session
            or receipt.tenant_id != self.tenant_id
            or receipt.endpoint != self.endpoint
            or receipt.entity_type != self.entity_type
            or receipt.status != "accepted"
            or self.received_at.utcoffset() is None
        ):
            raise ValueError(
                "neutral source creation effect does not match attached native receipt"
            )
        values = command_scope(self.request, self.tenant_id)
        expected_count = (
            len(self.request.members)
            if isinstance(self.request, RegistryChunkInput)
            else len(self.request.selections)
            if isinstance(self.request, FinancialChunkInput)
            else 1
        )
        if receipt.accepted_count != expected_count:
            raise ValueError("native neutral receipt count does not match command")
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {
                "scope": canonical_content_hash(
                    {key: value for key, value in values.items() if key != "revision"}
                )
            },
        )
        if command_kind(self.request)[1]:
            await self._chunk(session, receipt, values)
            if not ingestion_job_transition_allowed(
                transition=IngestionJobTransition.ACCEPTED_TO_COMPLETED,
                current_status=receipt.status,
            ):
                raise ValueError("invalid native chunk receipt transition")
            receipt.status = "completed"
            receipt.completed_at = await session.scalar(select(func.clock_timestamp()))
        else:
            await self._seal(session, receipt, values)
        await session.flush()

    async def _chunk(self, session, receipt, values):
        request = self.request
        registry = isinstance(request, RegistryChunkInput)
        records = request.members if registry else request.selections
        raw_hash = require_chunk_budget(self.raw_bytes, len(records))
        existing = await session.scalar(
            select(FinancialSourceChunkRow).where(
                *exact_scope(FinancialSourceChunkRow, values),
                FinancialSourceChunkRow.chunk_index == request.chunk_index,
            )
        )
        if existing is not None:
            require_custody_replay(
                existing.typed_hash,
                existing.raw_hash,
                typed_hash=request.typed_content_hash,
                raw_hash=raw_hash,
            )
            raise ObservationConflict("SOURCE_CHUNK_EXISTING_RECEIPT_REQUIRED")
        sealed = await session.scalar(
            select(FinancialSourceCutRow).where(*exact_scope(FinancialSourceCutRow, values))
        )
        if sealed is not None:
            raise ObservationConflict("SOURCE_CUT_ALREADY_SEALED")
        session.add(
            FinancialSourceChunkRow(
                **values,
                chunk_index=request.chunk_index,
                typed_hash=request.typed_content_hash,
                raw_hash=raw_hash,
                raw_bytes=self.raw_bytes,
                row_count=len(records),
                received_at=self.received_at,
                receipt_job_id=receipt.job_id,
            )
        )
        await session.flush()
        previous = None
        for record in records:
            key = (
                (record.provider_namespace, record.source_member_id)
                if registry
                else (record.portfolio_id,)
            )
            if previous is not None and key <= previous:
                raise ObservationConflict("SOURCE_CHUNK_ORDER_OR_DUPLICATE")
            previous = key
            portfolio = record.core_portfolio_id if registry else record.portfolio_id
            if portfolio is not None:
                owned = await session.scalar(
                    select(Portfolio.portfolio_id).where(
                        Portfolio.tenant_id == self.tenant_id, Portfolio.portfolio_id == portfolio
                    )
                )
                if owned is None:
                    raise ObservationConflict("SOURCE_MEMBER_PORTFOLIO_NOT_OWNED")
            if isinstance(record, RegistryMemberInput):
                domain = record.to_domain()
                session.add(
                    HistoricalRegistryMemberRow(
                        **values,
                        provider_namespace=record.provider_namespace,
                        source_member_id=record.source_member_id,
                        chunk_index=request.chunk_index,
                        core_portfolio_id=portfolio,
                        member_revision=record.member_revision,
                        content_hash=domain.content_hash,
                        declaration=record.model_dump(mode="json"),
                    )
                )
            else:
                session.add(
                    FinancialSourceInputRow(
                        **values,
                        portfolio_id=portfolio,
                        chunk_index=request.chunk_index,
                        content_hash=financial_input_hash(record),
                        declaration=record.model_dump(mode="json"),
                    )
                )
        await flush_unique_source_rows(session)

    async def _seal(self, session, receipt, values):
        request = self.request
        raw_hash = require_chunk_budget(self.raw_bytes, 1)
        declaration = request.model_dump(mode="json")
        content_hash = request.to_domain(self.tenant_id).content_hash
        existing = await session.scalar(
            select(FinancialSourceCutRow).where(*exact_scope(FinancialSourceCutRow, values))
        )
        if existing is not None:
            require_custody_replay(
                existing.content_hash, existing.raw_hash, typed_hash=content_hash, raw_hash=raw_hash
            )
            raise ObservationConflict("SOURCE_SEAL_EXISTING_RECEIPT_REQUIRED")
        # Admission observes indexed chunk cardinality only; worker revalidates actual
        # raw bytes, ordered roots and members in restartable bounded steps.
        counts = (
            await session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(FinancialSourceChunkRow.row_count), 0),
                    func.min(FinancialSourceChunkRow.chunk_index),
                    func.max(FinancialSourceChunkRow.chunk_index),
                ).where(*exact_scope(FinancialSourceChunkRow, values))
            )
        ).one()
        expected = (
            request.supplied_count
            if isinstance(request, RegistrySealInput)
            else request.selection_count
        )
        count, rows, low, high = counts
        if (
            count != request.chunk_count
            or rows != expected
            or (count and (low != 0 or high != count - 1))
        ):
            raise ObservationConflict("SOURCE_SEAL_CHUNK_CARDINALITY_MISMATCH")
        head_scope = {key: value for key, value in values.items() if key != "revision"}
        head = await session.scalar(
            select(FinancialSourceHeadRow)
            .where(*exact_scope(FinancialSourceHeadRow, head_scope))
            .with_for_update()
        )
        if head is None:
            if request.revision != 1 or request.expected_head_hash is not None:
                raise ObservationConflict("SOURCE_SEAL_STALE_HEAD")
        elif (
            request.revision != head.revision + 1
            or request.expected_head_hash != head.content_hash
            or request.predecessor_hash != head.content_hash
        ):
            raise ObservationConflict("SOURCE_SEAL_STALE_HEAD")
        if head is not None:
            predecessor_status = await session.scalar(
                select(FinancialSourceCutWorkRow.status).where(
                    *exact_scope(FinancialSourceCutWorkRow, head_scope),
                    FinancialSourceCutWorkRow.revision == head.revision,
                    FinancialSourceCutWorkRow.partition_index == 0,
                    FinancialSourceCutWorkRow.content_hash == head.content_hash,
                )
            )
            # A correction can repair a failed predecessor, but may not overtake
            # its pending custody transaction and reverse scoped notice order.
            if predecessor_status not in {"COMPLETED", "FAILED"}:
                raise ObservationConflict("SOURCE_SEAL_PREDECESSOR_CUSTODY_PENDING")
        session.add(
            FinancialSourceCutRow(
                **values,
                content_hash=content_hash,
                raw_hash=raw_hash,
                raw_bytes=self.raw_bytes,
                declaration=declaration,
                row_count=rows,
                chunk_count=count,
                received_at=self.received_at,
                receipt_job_id=receipt.job_id,
            )
        )
        await session.flush()
        if head is None:
            session.add(FinancialSourceHeadRow(**values, content_hash=content_hash))
        else:
            head.revision, head.content_hash = request.revision, content_hash
        session.add(
            FinancialSourceCutWorkRow(
                work_id=str(uuid4()),
                partition_index=0,
                **values,
                content_hash=content_hash,
                receipt_job_id=receipt.job_id,
                checkpoint={"stage": "VERIFY_CHUNKS", "verified_rows": 0},
            )
        )
