# src/libs/portfolio-common/portfolio_common/valuation_job_repository.py
import logging
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import and_, case, func, literal, not_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import PortfolioValuationJob
from .durable_correlation import durable_correlation_diagnostics
from .infrastructure.persistence.statement_batching import (
    StatementBatchOperation,
    iter_statement_chunks,
    observe_multi_statement_batch,
)
from .logging_utils import normalize_lineage_value
from .valuation_job_contracts import ValuationJobUpsert

logger = logging.getLogger(__name__)


class ValuationJobRepository:
    """
    Handles database operations for creating and managing PortfolioValuationJob records.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_job(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
        epoch: int,
        correlation_id: Optional[str] = None,
        source_correction_id: Optional[str] = None,
        rearm_completed: bool = False,
        requeue_if_processing: bool = False,
    ) -> int:
        """
        Idempotently creates or updates a valuation job.

        Duplicate scheduler polls for the same logical run must not re-arm an already completed
        or failed valuation job. Correlation is diagnostic lineage, not rearm authority.
        Source-correction callers must request terminal-job rearming explicitly after proving
        source freshness.
        They can also preserve a different source observation that arrives during PROCESSING;
        ordinary readiness callers remain non-disruptive. Transport correlation remains
        diagnostic and is never used as source-correction identity.
        """
        return await self._upsert_jobs(
            [
                ValuationJobUpsert(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    valuation_date=valuation_date,
                    epoch=epoch,
                    correlation_id=correlation_id,
                    source_correction_id=source_correction_id,
                )
            ],
            rearm_completed=rearm_completed,
            requeue_if_processing=requeue_if_processing,
        )

    async def upsert_jobs(
        self,
        jobs: Iterable[ValuationJobUpsert],
        *,
        rearm_completed: bool = False,
        requeue_if_processing: bool = False,
    ) -> int:
        return await self._upsert_jobs(
            jobs,
            rearm_completed=rearm_completed,
            requeue_if_processing=requeue_if_processing,
            fence_by_readiness_sequence=False,
        )

    async def upsert_position_readiness_job(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
        epoch: int,
        correlation_id: Optional[str],
        source_mutation_id: str,
        readiness_outbox_id: int,
    ) -> int:
        """Schedule readiness only when persisted position authority is newer.

        The valuation worker snapshots the exact-scope readiness outbox ID when it claims
        a job. A readiness event may arrive after that claim even though its position mutation
        was already visible. Comparing durable sequence authority prevents that delivery race from
        fabricating a second valuation while preserving requeue for a genuinely later mutation.
        """

        if readiness_outbox_id <= 0:
            raise ValueError("readiness_outbox_id must be a positive integer")

        return await self._upsert_jobs(
            [
                ValuationJobUpsert(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    valuation_date=valuation_date,
                    epoch=epoch,
                    correlation_id=correlation_id,
                    source_correction_id=source_mutation_id,
                    readiness_outbox_id=readiness_outbox_id,
                )
            ],
            rearm_completed=True,
            requeue_if_processing=True,
            fence_by_readiness_sequence=True,
        )

    async def _upsert_jobs(
        self,
        jobs: Iterable[ValuationJobUpsert],
        *,
        rearm_completed: bool,
        requeue_if_processing: bool,
        fence_by_readiness_sequence: bool = False,
    ) -> int:
        normalized_jobs = self._normalize_jobs(jobs)
        if not normalized_jobs:
            return 0
        if requeue_if_processing and any(
            job.source_correction_id is None for job in normalized_jobs
        ):
            raise ValueError(
                "source_correction_id is required when requeue_if_processing is enabled"
            )

        try:
            latest_epochs_by_scope = await self.get_latest_epochs_for_scopes(normalized_jobs)
            eligible_jobs = self._eligible_jobs(normalized_jobs, latest_epochs_by_scope)

            if not eligible_jobs:
                return 0

            staged_count = await self._execute_upsert_jobs(
                eligible_jobs,
                rearm_completed=rearm_completed,
                requeue_if_processing=requeue_if_processing,
                fence_by_readiness_sequence=fence_by_readiness_sequence,
            )
            superseded_count = await self._skip_superseded_pending_jobs(
                normalized_jobs=normalized_jobs,
                latest_epochs_by_scope=latest_epochs_by_scope,
            )
            _log_staged_job_upsert(
                requested_count=len(normalized_jobs),
                eligible_count=len(eligible_jobs),
                staged_count=staged_count,
                superseded_count=superseded_count,
            )
            return staged_count
        except Exception:
            logger.error(
                "Failed to stage valuation job upserts",
                extra={
                    "job_count": len(normalized_jobs),
                },
                exc_info=True,
            )
            raise

    def _eligible_jobs(
        self,
        normalized_jobs: list[ValuationJobUpsert],
        latest_epochs_by_scope: dict[tuple[str, str, date], int],
    ) -> list[ValuationJobUpsert]:
        return [
            job for job in normalized_jobs if not self._is_stale_job(job, latest_epochs_by_scope)
        ]

    async def _execute_upsert_jobs(
        self,
        eligible_jobs: list[ValuationJobUpsert],
        *,
        rearm_completed: bool,
        requeue_if_processing: bool,
        fence_by_readiness_sequence: bool = False,
    ) -> int:
        staged_count = 0
        observe_multi_statement_batch(
            operation=StatementBatchOperation.VALUATION_JOB_UPSERT,
            item_count=len(eligible_jobs),
            binds_per_row=11,
            reserved_binds=16,
        )
        for job_chunk in iter_statement_chunks(
            eligible_jobs,
            binds_per_row=11,
            reserved_binds=16,
        ):
            result = await self.db.execute(
                _valuation_job_upsert_stmt(
                    job_chunk,
                    rearm_completed=rearm_completed,
                    requeue_if_processing=requeue_if_processing,
                    fence_by_readiness_sequence=fence_by_readiness_sequence,
                ).returning(
                    PortfolioValuationJob.portfolio_id,
                    PortfolioValuationJob.security_id,
                    PortfolioValuationJob.valuation_date,
                    PortfolioValuationJob.epoch,
                )
            )
            staged_count += len(result.all())
        return staged_count

    def _normalize_jobs(self, jobs: Iterable[ValuationJobUpsert]) -> list[ValuationJobUpsert]:
        normalized_by_scope: dict[tuple[str, str, date, int], ValuationJobUpsert] = {}
        for job in jobs:
            normalized_job = ValuationJobUpsert(
                portfolio_id=job.portfolio_id,
                security_id=job.security_id,
                valuation_date=job.valuation_date,
                epoch=job.epoch,
                correlation_id=normalize_lineage_value(job.correlation_id),
                source_correction_id=normalize_lineage_value(job.source_correction_id),
                readiness_outbox_id=job.readiness_outbox_id,
            )
            normalized_by_scope[
                (
                    normalized_job.portfolio_id,
                    normalized_job.security_id,
                    normalized_job.valuation_date,
                    normalized_job.epoch,
                )
            ] = normalized_job
        # PostgreSQL acquires row and unique-index locks in VALUES order. Every caller must use
        # the same order so overlapping scheduler, price, FX, and readiness transactions cannot
        # form an inverted lock cycle while upserting the same valuation-job scopes.
        return [normalized_by_scope[scope] for scope in sorted(normalized_by_scope)]

    def _is_stale_job(
        self,
        job: ValuationJobUpsert,
        latest_epochs_by_scope: dict[tuple[str, str, date], int],
    ) -> bool:
        latest_epoch = latest_epochs_by_scope.get(
            (job.portfolio_id, job.security_id, job.valuation_date)
        )
        if latest_epoch is not None and latest_epoch > job.epoch:
            logger.info(
                "Skipping stale valuation job upsert because a newer epoch already exists",
                extra={
                    "portfolio_id": job.portfolio_id,
                    "security_id": job.security_id,
                    "valuation_date": job.valuation_date,
                    "incoming_epoch": job.epoch,
                    "latest_epoch": latest_epoch,
                },
            )
            return True
        return False

    async def get_latest_epoch_for_scope(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
    ) -> int | None:
        result = await self.db.execute(
            select(func.max(PortfolioValuationJob.epoch)).where(
                PortfolioValuationJob.portfolio_id == portfolio_id,
                PortfolioValuationJob.security_id == security_id,
                PortfolioValuationJob.valuation_date == valuation_date,
            )
        )
        latest_epoch = result.scalar_one_or_none()
        return int(latest_epoch) if latest_epoch is not None else None

    async def get_latest_epochs_for_scopes(
        self, jobs: Iterable[ValuationJobUpsert]
    ) -> dict[tuple[str, str, date], int]:
        scopes = sorted({(job.portfolio_id, job.security_id, job.valuation_date) for job in jobs})
        if not scopes:
            return {}

        latest_epochs: dict[tuple[str, str, date], int] = {}
        observe_multi_statement_batch(
            operation=StatementBatchOperation.VALUATION_JOB_EPOCH_LOOKUP,
            item_count=len(scopes),
            binds_per_row=3,
        )
        for scope_chunk in iter_statement_chunks(scopes, binds_per_row=3):
            result = await self.db.execute(
                select(
                    PortfolioValuationJob.portfolio_id,
                    PortfolioValuationJob.security_id,
                    PortfolioValuationJob.valuation_date,
                    func.max(PortfolioValuationJob.epoch),
                )
                .where(
                    tuple_(
                        PortfolioValuationJob.portfolio_id,
                        PortfolioValuationJob.security_id,
                        PortfolioValuationJob.valuation_date,
                    ).in_(scope_chunk)
                )
                .group_by(
                    PortfolioValuationJob.portfolio_id,
                    PortfolioValuationJob.security_id,
                    PortfolioValuationJob.valuation_date,
                )
            )
            latest_epochs.update(
                {
                    (portfolio_id, security_id, valuation_date): latest_epoch
                    for portfolio_id, security_id, valuation_date, latest_epoch in result.all()
                }
            )
        return latest_epochs

    async def _skip_superseded_pending_jobs(
        self,
        *,
        normalized_jobs: list[ValuationJobUpsert],
        latest_epochs_by_scope: dict[tuple[str, str, date], int],
    ) -> int:
        latest_epoch_targets: dict[tuple[str, str, date], int] = {}
        for job in normalized_jobs:
            scope = (job.portfolio_id, job.security_id, job.valuation_date)
            latest_epoch_targets[scope] = max(
                latest_epochs_by_scope.get(scope, job.epoch),
                latest_epoch_targets.get(scope, job.epoch),
                job.epoch,
            )

        skipped_count = 0
        for (
            portfolio_id,
            security_id,
            valuation_date,
        ), latest_epoch in latest_epoch_targets.items():
            stmt = (
                update(PortfolioValuationJob)
                .where(
                    PortfolioValuationJob.portfolio_id == portfolio_id,
                    PortfolioValuationJob.security_id == security_id,
                    PortfolioValuationJob.valuation_date == valuation_date,
                    PortfolioValuationJob.status == "PENDING",
                    PortfolioValuationJob.epoch < latest_epoch,
                )
                .values(
                    status="SKIPPED_SUPERSEDED",
                    failure_reason="Superseded by newer valuation epoch.",
                    updated_at=func.now(),
                )
                .returning(PortfolioValuationJob.id)
            )
            result = await self.db.execute(stmt)
            skipped_count += len(result.fetchall())
        return skipped_count


def _valuation_job_upsert_stmt(
    eligible_jobs: list[ValuationJobUpsert],
    *,
    rearm_completed: bool = False,
    requeue_if_processing: bool = False,
    fence_by_readiness_sequence: bool = False,
):
    readiness_outbox_id: int | None = None
    if fence_by_readiness_sequence:
        if len(eligible_jobs) != 1 or eligible_jobs[0].readiness_outbox_id is None:
            raise ValueError("Readiness-sequence fencing requires exactly one sequenced job")
        readiness_outbox_id = eligible_jobs[0].readiness_outbox_id
    stmt = pg_insert(PortfolioValuationJob).values(_valuation_job_insert_values(eligible_jobs))
    return stmt.on_conflict_do_update(
        index_elements=["portfolio_id", "security_id", "valuation_date", "epoch"],
        set_=_valuation_job_update_values(
            stmt,
            requeue_if_processing=requeue_if_processing,
        ),
        where=_valuation_job_conflict_update_predicate(
            stmt,
            rearm_completed=rearm_completed,
            requeue_if_processing=requeue_if_processing,
            fence_by_readiness_sequence=fence_by_readiness_sequence,
            readiness_outbox_id=readiness_outbox_id,
        ),
    )


def _valuation_job_insert_values(
    eligible_jobs: list[ValuationJobUpsert],
) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for job in eligible_jobs:
        diagnostics = durable_correlation_diagnostics(
            correlation_id=job.correlation_id,
            record_family="valuation_job",
            portfolio_id=job.portfolio_id,
            security_id=job.security_id,
            valuation_date=job.valuation_date,
            epoch=job.epoch,
        )
        values.append(
            {
                "portfolio_id": job.portfolio_id,
                "security_id": job.security_id,
                "valuation_date": job.valuation_date,
                "epoch": job.epoch,
                "status": "PENDING",
                "requeue_requested": False,
                "source_correction_id": job.source_correction_id,
                # Only a claim's exact-scope database query may advance covered authority.
                "claimed_readiness_outbox_id": 0,
                "correlation_id": diagnostics.correlation_id,
                "correlation_missing_reason": diagnostics.correlation_missing_reason,
                "alternate_lookup_key": diagnostics.alternate_lookup_key,
            }
        )
    return values


def _valuation_job_update_values(
    stmt,
    *,
    requeue_if_processing: bool,
) -> dict[str, object]:
    values: dict[str, object] = {
        "status": "PENDING",
        "failure_reason": None,
        "requeue_requested": False,
        "source_correction_id": stmt.excluded.source_correction_id,
        "correlation_id": stmt.excluded.correlation_id,
        "correlation_missing_reason": stmt.excluded.correlation_missing_reason,
        "alternate_lookup_key": stmt.excluded.alternate_lookup_key,
        "updated_at": func.now(),
    }
    if requeue_if_processing:
        values.update(
            status=case(
                (
                    PortfolioValuationJob.status == "PROCESSING",
                    PortfolioValuationJob.status,
                ),
                else_="PENDING",
            ),
            requeue_requested=case(
                (PortfolioValuationJob.status == "PROCESSING", True),
                else_=False,
            ),
        )
    return values


def _valuation_job_conflict_update_predicate(
    stmt,
    *,
    rearm_completed: bool,
    requeue_if_processing: bool,
    fence_by_readiness_sequence: bool,
    readiness_outbox_id: int | None,
):
    identity_matches = PortfolioValuationJob.correlation_id.is_not_distinct_from(
        stmt.excluded.correlation_id
    )
    if requeue_if_processing:
        identity_matches = PortfolioValuationJob.source_correction_id.is_not_distinct_from(
            stmt.excluded.source_correction_id
        )
        same_source = and_(
            PortfolioValuationJob.status.in_(("PENDING", "PROCESSING", "COMPLETE")),
            identity_matches,
        )
        predicate = not_(same_source)
    else:
        same_pending_lineage = and_(
            PortfolioValuationJob.status == "PENDING",
            identity_matches,
        )
        predicate = not_(PortfolioValuationJob.status == "PROCESSING") & not_(same_pending_lineage)
    if not rearm_completed:
        predicate &= PortfolioValuationJob.status.not_in(("COMPLETE", "FAILED"))
    if fence_by_readiness_sequence:
        if readiness_outbox_id is None:
            raise ValueError("readiness_outbox_id is required for sequence fencing")
        predicate &= literal(readiness_outbox_id) > (
            PortfolioValuationJob.claimed_readiness_outbox_id
        )
    return predicate


def _log_staged_job_upsert(
    *,
    requested_count: int,
    eligible_count: int,
    staged_count: int,
    superseded_count: int,
) -> None:
    logger.debug(
        "Staged valuation job upserts",
        extra={
            "requested_count": requested_count,
            "eligible_count": eligible_count,
            "staged_count": staged_count,
            "superseded_count": superseded_count,
        },
    )
