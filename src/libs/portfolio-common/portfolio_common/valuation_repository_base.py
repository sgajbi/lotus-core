import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Integer, and_, any_, case, cast, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .config import DEFAULT_BUSINESS_CALENDAR_CODE
from .database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    MarketPrice,
    OutboxEvent,
    Portfolio,
    PortfolioValuationJob,
    PositionHistory,
    PositionState,
)
from .domain.currency import normalize_currency_code
from .domain.valuation.position_state import SCHEDULABLE_POSITION_STATE_STATUSES
from .identifiers import normalize_lookup_identifier
from .infrastructure.persistence.statement_batching import (
    POSTGRES_STATEMENT_ROW_LIMIT,
    StatementBatchOperation,
    iter_statement_chunks,
    observe_multi_statement_batch,
)
from .utils import async_timed
from .valuation_job_contracts import ValuationJobTransitionOutcome
from .valuation_runtime_settings import effective_valuation_job_claim_cohort_size
from .valuation_snapshot_contiguity import (
    build_contiguous_snapshot_dates_stmt,
    contiguous_snapshot_dates_by_key,
)

logger = logging.getLogger(__name__)

_VALUATION_JOB_CLAIM_LOCK_ID = 7_611_901
_VALUATION_LEASE_OWNER_MAX_LENGTH = 128
_STALE_SUPERSEDED_RESERVED_BINDS = 7
_STALE_FAILED_RESERVED_BINDS = 7
_STALE_RESET_RESERVED_BINDS = 6


@dataclass(frozen=True, slots=True)
class _ContiguousStateKey:
    portfolio_id: str
    security_id: str
    epoch: int


def _normalize_contiguous_states(states: List[PositionState]) -> List[_ContiguousStateKey]:
    """Collapse duplicate state objects and reject ambiguous output-key epochs."""

    normalized: dict[tuple[str, str], _ContiguousStateKey] = {}
    for state in states:
        output_key = (state.portfolio_id, state.security_id)
        existing = normalized.get(output_key)
        if existing is not None and existing.epoch != state.epoch:
            raise ValueError("conflicting position-state epochs for one contiguous-date key")
        normalized[output_key] = _ContiguousStateKey(
            portfolio_id=state.portfolio_id,
            security_id=state.security_id,
            epoch=state.epoch,
        )
    return [normalized[key] for key in sorted(normalized)]


def _latest_readiness_outbox_id_for_job():
    """Return the latest committed readiness sequence for the exact valuation scope."""

    aggregate_id = func.concat(
        PortfolioValuationJob.portfolio_id,
        ":",
        PortfolioValuationJob.security_id,
        ":",
        func.to_char(PortfolioValuationJob.valuation_date, "YYYY-MM-DD"),
        ":",
        PortfolioValuationJob.epoch,
    )
    return func.coalesce(
        select(func.max(OutboxEvent.id))
        .where(
            OutboxEvent.aggregate_type == "ValuationReadiness",
            OutboxEvent.event_type == "PortfolioDayReadyForValuation",
            OutboxEvent.aggregate_id == aggregate_id,
            OutboxEvent.payload["portfolio_id"].as_string() == PortfolioValuationJob.portfolio_id,
            OutboxEvent.payload["security_id"].as_string() == PortfolioValuationJob.security_id,
            OutboxEvent.payload["valuation_date"].as_string()
            == func.to_char(PortfolioValuationJob.valuation_date, "YYYY-MM-DD"),
            OutboxEvent.payload["epoch"].as_integer() == PortfolioValuationJob.epoch,
        )
        .scalar_subquery(),
        0,
    )


class ValuationRepositoryBase:
    """Shared query/claim logic for valuation worker services."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._default_lease_owner = f"valuation-repository-{uuid.uuid4().hex}"

    @staticmethod
    def _normalize_currency_code(currency_code: str) -> str:
        return normalize_currency_code(currency_code)

    def _observe_jobs_claimed(self, claimed_count: int) -> None:
        """Hook for service-local metrics."""

    def _observe_stale_resets(self, reset_count: int) -> None:
        """Hook for service-local metrics."""

    def _observe_lease_transition(self, stage: str, outcome: str, count: int) -> None:
        """Hook for bounded service-local lease lifecycle metrics."""

    @staticmethod
    def _newer_epoch_exists(current_job, newer_job):
        return (
            select(newer_job.id)
            .where(
                newer_job.portfolio_id == current_job.portfolio_id,
                newer_job.security_id == current_job.security_id,
                newer_job.valuation_date == current_job.valuation_date,
                newer_job.epoch > current_job.epoch,
            )
            .exists()
        )

    @staticmethod
    def _latest_epoch_for_job(current_job, latest_job):
        """Resolve the latest durable epoch through the identity index."""

        return (
            select(latest_job.epoch)
            .where(
                latest_job.portfolio_id == current_job.portfolio_id,
                latest_job.security_id == current_job.security_id,
                latest_job.valuation_date == current_job.valuation_date,
            )
            .order_by(latest_job.epoch.desc())
            .limit(1)
            .scalar_subquery()
        )

    @async_timed(
        repository="ValuationRepository",
        method="find_position_keys_requiring_price_revaluation",
    )
    async def find_position_keys_requiring_price_revaluation(
        self, security_id: str, a_date: date
    ) -> List[Tuple[str, str, int]]:
        """Return current epochs whose latest derived authority predates the price."""

        latest_history_subquery = (
            select(
                PositionHistory.portfolio_id.label("portfolio_id"),
                PositionHistory.security_id.label("security_id"),
                PositionHistory.epoch.label("epoch"),
                PositionHistory.quantity.label("quantity"),
                PositionHistory.updated_at.label("updated_at"),
            )
            .where(
                PositionHistory.security_id == security_id,
                PositionHistory.position_date <= a_date,
            )
            .distinct(PositionHistory.portfolio_id, PositionHistory.epoch)
            .order_by(
                PositionHistory.portfolio_id,
                PositionHistory.epoch,
                PositionHistory.position_date.desc(),
                PositionHistory.id.desc(),
            )
            .subquery()
        )

        stmt = (
            select(
                latest_history_subquery.c.portfolio_id,
                latest_history_subquery.c.security_id,
                latest_history_subquery.c.epoch,
            )
            .join(
                PositionState,
                (PositionState.portfolio_id == latest_history_subquery.c.portfolio_id)
                & (PositionState.security_id == latest_history_subquery.c.security_id)
                & (PositionState.epoch == latest_history_subquery.c.epoch),
            )
            .join(
                MarketPrice,
                (MarketPrice.security_id == latest_history_subquery.c.security_id)
                & (MarketPrice.price_date == a_date),
            )
            .outerjoin(
                DailyPositionSnapshot,
                (DailyPositionSnapshot.portfolio_id == latest_history_subquery.c.portfolio_id)
                & (DailyPositionSnapshot.security_id == latest_history_subquery.c.security_id)
                & (DailyPositionSnapshot.date == a_date)
                & (DailyPositionSnapshot.epoch == latest_history_subquery.c.epoch),
            )
            .where(
                latest_history_subquery.c.quantity != 0,
                func.coalesce(
                    DailyPositionSnapshot.updated_at,
                    latest_history_subquery.c.updated_at,
                )
                < MarketPrice.updated_at,
            )
        )

        result = await self.db.execute(stmt)
        return [(row.portfolio_id, row.security_id, row.epoch) for row in result.all()]

    @async_timed(
        repository="ValuationRepository", method="find_portfolios_holding_security_on_date"
    )
    async def find_portfolios_holding_security_on_date(
        self, security_id: str, a_date: date
    ) -> List[str]:
        latest_history_subquery = (
            select(
                PositionHistory.portfolio_id,
                PositionHistory.quantity,
            )
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == PositionHistory.portfolio_id,
                    PositionState.security_id == PositionHistory.security_id,
                    PositionState.epoch == PositionHistory.epoch,
                ),
            )
            .where(
                PositionHistory.security_id == security_id,
                PositionHistory.position_date <= a_date,
            )
            .distinct(PositionHistory.portfolio_id)
            .order_by(
                PositionHistory.portfolio_id,
                PositionHistory.position_date.desc(),
                PositionHistory.id.desc(),
            )
            .subquery()
        )

        stmt = select(latest_history_subquery.c.portfolio_id).where(
            latest_history_subquery.c.quantity != 0
        )

        result = await self.db.execute(stmt)
        portfolio_ids = result.scalars().all()
        logger.info(
            "Found %s portfolios holding '%s' on or before %s.",
            len(portfolio_ids),
            security_id,
            a_date,
        )
        return portfolio_ids

    @async_timed(
        repository="ValuationRepository", method="find_portfolios_first_holding_security_after_date"
    )
    async def find_portfolios_first_holding_security_after_date(
        self, security_id: str, a_date: date
    ) -> List[str]:
        stmt = (
            select(func.distinct(PositionHistory.portfolio_id))
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == PositionHistory.portfolio_id,
                    PositionState.security_id == PositionHistory.security_id,
                    PositionState.epoch == PositionHistory.epoch,
                ),
            )
            .where(
                PositionHistory.security_id == security_id,
                PositionHistory.position_date > a_date,
                PositionHistory.quantity != 0,
            )
            .order_by(PositionHistory.portfolio_id.asc())
        )

        result = await self.db.execute(stmt)
        portfolio_ids = result.scalars().all()
        logger.info(
            "Found %s portfolios first holding '%s' after %s.",
            len(portfolio_ids),
            security_id,
            a_date,
        )
        return portfolio_ids

    @async_timed(repository="ValuationRepository", method="get_portfolios_by_ids")
    async def get_portfolios_by_ids(self, portfolio_ids: List[str]) -> List[Portfolio]:
        normalized_portfolio_ids = [
            normalized
            for portfolio_id in portfolio_ids
            if (normalized := normalize_lookup_identifier(portfolio_id))
        ]
        if not normalized_portfolio_ids:
            return []
        stmt = select(Portfolio).where(
            func.trim(Portfolio.portfolio_id).in_(normalized_portfolio_ids)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="get_lagging_states")
    async def get_lagging_states(
        self, latest_business_date: date, limit: int
    ) -> List[PositionState]:
        stmt = (
            select(PositionState)
            .where(
                PositionState.watermark_date < latest_business_date,
                PositionState.status.in_(SCHEDULABLE_POSITION_STATE_STATUSES),
            )
            .order_by(
                PositionState.updated_at.asc(),
                PositionState.portfolio_id.asc(),
                PositionState.security_id.asc(),
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="get_terminal_reprocessing_states")
    async def get_terminal_reprocessing_states(
        self, latest_business_date: date, limit: int
    ) -> List[PositionState]:
        stmt = (
            select(PositionState)
            .where(
                PositionState.status == "REPROCESSING",
                PositionState.watermark_date >= latest_business_date,
            )
            .order_by(
                PositionState.updated_at.asc(),
                PositionState.portfolio_id.asc(),
                PositionState.security_id.asc(),
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="find_contiguous_snapshot_dates")
    async def find_contiguous_snapshot_dates(
        self,
        states: List[PositionState],
        first_open_dates: Optional[Dict[Tuple[str, str, int], date]] = None,
        latest_valuation_date: date | None = None,
    ) -> Dict[Tuple[str, str], date]:
        if not states:
            return {}

        normalized_states = _normalize_contiguous_states(states)
        all_first_open_dates = dict(first_open_dates or {})
        if latest_valuation_date is None:
            latest_valuation_date = await self.get_latest_business_date()
        if latest_valuation_date is None:
            return {}

        contiguous_dates: Dict[Tuple[str, str], date] = {}
        observe_multi_statement_batch(
            operation=StatementBatchOperation.CONTIGUOUS_SNAPSHOT_LOOKUP,
            item_count=len(normalized_states),
            binds_per_row=7,
            reserved_binds=11,
        )
        for state_chunk in iter_statement_chunks(
            normalized_states,
            binds_per_row=7,
            reserved_binds=11,
        ):
            chunk_keys = {
                (state.portfolio_id, state.security_id, state.epoch) for state in state_chunk
            }
            chunk_first_open_dates = {
                key: first_open_date
                for key, first_open_date in all_first_open_dates.items()
                if key in chunk_keys
            }
            result = await self.db.execute(
                build_contiguous_snapshot_dates_stmt(
                    list(state_chunk),
                    chunk_first_open_dates,
                    latest_valuation_date,
                )
            )
            contiguous_dates.update(contiguous_snapshot_dates_by_key(result))
        return contiguous_dates

    @async_timed(repository="ValuationRepository", method="get_valuation_dates_between")
    async def get_valuation_dates_between(
        self,
        after_date: date,
        through_date: date,
    ) -> list[date]:
        calendar_exists_stmt = select(
            select(BusinessDate.date)
            .where(BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE)
            .exists()
        )
        calendar_exists = bool((await self.db.execute(calendar_exists_stmt)).scalar_one())
        if not calendar_exists:
            day_count = (through_date - after_date).days
            return [after_date + timedelta(days=offset) for offset in range(1, day_count + 1)]

        valuation_dates_stmt = (
            select(BusinessDate.date)
            .where(
                BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE,
                BusinessDate.date > after_date,
                BusinessDate.date <= through_date,
            )
            .order_by(BusinessDate.date.asc())
        )
        result = await self.db.execute(valuation_dates_stmt)
        return list(result.scalars().all())

    @async_timed(repository="ValuationRepository", method="get_states_needing_backfill")
    async def get_states_needing_backfill(
        self, latest_business_date: date, limit: int
    ) -> List[PositionState]:
        stmt = (
            select(PositionState)
            .join(
                Instrument,
                func.trim(Instrument.security_id) == func.trim(PositionState.security_id),
            )
            .where(
                PositionState.watermark_date < latest_business_date,
                PositionState.status.in_(SCHEDULABLE_POSITION_STATE_STATUSES),
            )
            .order_by(
                PositionState.updated_at.asc(),
                PositionState.portfolio_id.asc(),
                PositionState.security_id.asc(),
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="get_last_position_history_before_date")
    async def get_last_position_history_before_date(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> Optional[PositionHistory]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = (
            select(PositionHistory)
            .filter(
                func.trim(PositionHistory.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionHistory.security_id) == normalized_security_id,
                PositionHistory.position_date <= a_date,
                PositionHistory.epoch == epoch,
            )
            .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_latest_business_date")
    async def get_latest_business_date(self) -> Optional[date]:
        business_date_stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
        )
        business_date = (await self.db.execute(business_date_stmt)).scalar_one_or_none()
        if business_date is not None:
            return business_date

        snapshot_date_stmt = select(func.max(DailyPositionSnapshot.date))
        valuation_job_date_stmt = select(func.max(PortfolioValuationJob.valuation_date))

        snapshot_date = (await self.db.execute(snapshot_date_stmt)).scalar_one_or_none()
        valuation_job_date = (await self.db.execute(valuation_job_date_stmt)).scalar_one_or_none()

        candidates = [
            d for d in (business_date, snapshot_date, valuation_job_date) if d is not None
        ]
        return max(candidates) if candidates else None

    @async_timed(repository="ValuationRepository", method="update_job_status")
    async def update_job_status(
        self,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
        epoch: int,
        status: str,
        failure_reason: Optional[str] = None,
        expected_claim_token: str | None = None,
    ) -> ValuationJobTransitionOutcome:
        terminal_status = case(
            (PortfolioValuationJob.requeue_requested.is_(True), "PENDING"),
            else_=status,
        )
        values_to_update = {
            "status": terminal_status,
            "requeue_requested": False,
            "updated_at": func.now(),
            "attempt_count": PortfolioValuationJob.attempt_count + 1,
            "failure_reason": case(
                (PortfolioValuationJob.requeue_requested.is_(True), None),
                else_=(
                    failure_reason
                    if failure_reason is not None
                    else PortfolioValuationJob.failure_reason
                ),
            ),
        }
        values_to_update.update(
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
        )

        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = (
            update(PortfolioValuationJob)
            .where(
                func.trim(PortfolioValuationJob.portfolio_id) == normalized_portfolio_id,
                func.trim(PortfolioValuationJob.security_id) == normalized_security_id,
                PortfolioValuationJob.valuation_date == valuation_date,
                PortfolioValuationJob.epoch == epoch,
                PortfolioValuationJob.status == "PROCESSING",
                PortfolioValuationJob.valuation_claim_token.is_not_distinct_from(
                    expected_claim_token
                ),
                PortfolioValuationJob.valuation_lease_expires_at > func.clock_timestamp(),
            )
            .values(**values_to_update)
            .returning(PortfolioValuationJob.status)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        applied_status = result.scalar_one_or_none()
        if applied_status is None:
            self._observe_lease_transition("completion", "lost", 1)
            return ValuationJobTransitionOutcome.NOT_OWNED
        if applied_status == status:
            return ValuationJobTransitionOutcome.TERMINAL_APPLIED
        if applied_status == "PENDING":
            return ValuationJobTransitionOutcome.REQUEUED
        raise RuntimeError(
            "Valuation job transition returned an unsupported applied status: "
            f"requested={status!r}, applied={applied_status!r}"
        )

    @async_timed(repository="ValuationRepository", method="recover_dispatch_failed_jobs")
    async def recover_dispatch_failed_jobs(
        self,
        job_claims: list[tuple[int, str]],
        *,
        max_attempts: int,
        failure_reason: str,
    ) -> dict[str, int]:
        normalized_claims: dict[int, str] = {}
        for job_id, claim_token in job_claims:
            existing_token = normalized_claims.get(job_id)
            if existing_token is not None and existing_token != claim_token:
                raise ValueError("conflicting valuation claim tokens for the same job")
            normalized_claims[job_id] = claim_token
        ordered_claims = sorted(normalized_claims.items())
        if not ordered_claims:
            return {"pending_count": 0, "failed_count": 0}

        failed_count = 0
        pending_count = 0
        observe_multi_statement_batch(
            operation=StatementBatchOperation.DISPATCH_RECOVERY_UPDATE,
            item_count=len(ordered_claims),
            binds_per_row=2,
            reserved_binds=8,
        )
        for claim_chunk in iter_statement_chunks(
            ordered_claims,
            binds_per_row=2,
            reserved_binds=8,
        ):
            failed_result = await self.db.execute(
                _dispatch_failed_valuation_jobs_update_stmt(
                    job_claims=list(claim_chunk),
                    max_attempts=max_attempts,
                    failure_reason=failure_reason,
                )
            )
            pending_result = await self.db.execute(
                _dispatch_retryable_valuation_jobs_update_stmt(
                    job_claims=list(claim_chunk),
                    max_attempts=max_attempts,
                    failure_reason=failure_reason,
                )
            )
            failed_count += int(failed_result.rowcount or 0)
            pending_count += int(pending_result.rowcount or 0)
        if failed_count or pending_count:
            logger.warning(
                "Recovered valuation scheduler dispatch failure.",
                extra={
                    "job_count": len(ordered_claims),
                    "pending_count": pending_count,
                    "failed_count": failed_count,
                    "max_attempts": max_attempts,
                },
            )
        self._observe_lease_transition("dispatch_recovery", "failed", failed_count)
        self._observe_lease_transition("dispatch_recovery", "requeued", pending_count)
        return {"pending_count": pending_count, "failed_count": failed_count}

    @async_timed(repository="ValuationRepository", method="find_and_claim_eligible_jobs")
    async def find_and_claim_eligible_jobs(
        self,
        batch_size: int,
        *,
        max_in_flight_jobs: int | None = None,
        lease_owner: str | None = None,
        lease_duration_seconds: int = 900,
    ) -> List[PortfolioValuationJob]:
        resolved_lease_owner = (lease_owner or self._default_lease_owner).strip()
        if (
            not resolved_lease_owner
            or len(resolved_lease_owner) > _VALUATION_LEASE_OWNER_MAX_LENGTH
        ):
            raise ValueError("valuation lease owner must contain 1 to 128 characters")
        if lease_duration_seconds < 1:
            raise ValueError("valuation lease duration must be positive")
        effective_batch_size = effective_valuation_job_claim_cohort_size(batch_size)
        if max_in_flight_jobs is not None:
            await self.db.execute(select(func.pg_advisory_xact_lock(_VALUATION_JOB_CLAIM_LOCK_ID)))
            processing_count = int(
                (
                    await self.db.execute(
                        select(func.count()).where(PortfolioValuationJob.status == "PROCESSING")
                    )
                ).scalar_one()
            )
            effective_batch_size = min(
                effective_batch_size,
                max(max_in_flight_jobs - processing_count, 0),
            )
            if effective_batch_size == 0:
                return []

        latest_epoch = aliased(PortfolioValuationJob)
        eligible_ids = (
            select(PortfolioValuationJob.id)
            .where(
                PortfolioValuationJob.status == "PENDING",
                PortfolioValuationJob.epoch
                == self._latest_epoch_for_job(PortfolioValuationJob, latest_epoch),
            )
            .order_by(
                PortfolioValuationJob.portfolio_id.asc(),
                PortfolioValuationJob.security_id.asc(),
                PortfolioValuationJob.valuation_date.asc(),
                PortfolioValuationJob.epoch.desc(),
            )
            .limit(effective_batch_size)
            .with_for_update(skip_locked=True)
        )
        locked_eligible_ids = eligible_ids.subquery()
        eligible_id_array = select(func.array_agg(locked_eligible_ids.c.id)).scalar_subquery()

        query = (
            update(PortfolioValuationJob)
            .where(PortfolioValuationJob.id == any_(cast(eligible_id_array, ARRAY(Integer))))
            .values(
                status="PROCESSING",
                requeue_requested=False,
                claimed_readiness_outbox_id=func.greatest(
                    PortfolioValuationJob.claimed_readiness_outbox_id,
                    _latest_readiness_outbox_id_for_job(),
                ),
                valuation_lease_owner=resolved_lease_owner,
                valuation_claim_token=uuid.uuid4().hex,
                valuation_lease_expires_at=func.clock_timestamp()
                + func.make_interval(0, 0, 0, 0, 0, 0, lease_duration_seconds),
                updated_at=func.now(),
                attempt_count=PortfolioValuationJob.attempt_count + 1,
            )
            .returning(PortfolioValuationJob)
        )

        result = await self.db.execute(query)
        claimed_models = list(result.scalars().all())
        if claimed_models:
            logger.info("Found and claimed %s eligible valuation jobs.", len(claimed_models))
            self._observe_jobs_claimed(len(claimed_models))
            self._observe_lease_transition("claim", "acquired", len(claimed_models))
        claimed_models.sort(
            key=lambda job: (job.portfolio_id, job.security_id, job.valuation_date, -job.epoch)
        )
        return claimed_models

    @async_timed(repository="ValuationRepository", method="get_job_queue_stats")
    async def get_job_queue_stats(self) -> Dict[str, Any]:
        newer_epoch = aliased(PortfolioValuationJob)
        actionable_pending = (
            PortfolioValuationJob.status == "PENDING"
        ) & ~self._newer_epoch_exists(PortfolioValuationJob, newer_epoch)
        stmt = select(
            func.count().filter(actionable_pending).label("pending_count"),
            func.count().filter(PortfolioValuationJob.status == "FAILED").label("failed_count"),
            func.min(PortfolioValuationJob.created_at)
            .filter(actionable_pending)
            .label("oldest_pending_created_at"),
        ).where(PortfolioValuationJob.status.in_(("PENDING", "FAILED")))
        row = (await self.db.execute(stmt)).one()
        return {
            "pending_count": int(row.pending_count or 0),
            "failed_count": int(row.failed_count or 0),
            "oldest_pending_created_at": row.oldest_pending_created_at,
        }

    @async_timed(repository="ValuationRepository", method="get_portfolio")
    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        stmt = select(Portfolio).where(func.trim(Portfolio.portfolio_id) == normalized_portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_instrument")
    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = select(Instrument).where(func.trim(Instrument.security_id) == normalized_security_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_fx_rate")
    async def get_fx_rate(
        self, from_currency: str, to_currency: str, a_date: date
    ) -> Optional[FxRate]:
        normalized_from_currency = self._normalize_currency_code(from_currency)
        normalized_to_currency = self._normalize_currency_code(to_currency)
        from_currency_expr = func.upper(func.trim(FxRate.from_currency))
        to_currency_expr = func.upper(func.trim(FxRate.to_currency))
        stmt = (
            select(FxRate)
            .filter(
                from_currency_expr == normalized_from_currency,
                to_currency_expr == normalized_to_currency,
                FxRate.rate_date <= a_date,
            )
            .order_by(FxRate.rate_date.desc(), FxRate.id.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_latest_price_for_position")
    async def get_latest_price_for_position(
        self, security_id: str, position_date: date
    ) -> Optional[MarketPrice]:
        normalized_security_id = normalize_lookup_identifier(security_id)
        market_price_security_id = func.trim(MarketPrice.security_id)
        stmt = (
            select(MarketPrice)
            .filter(
                market_price_security_id == normalized_security_id,
                MarketPrice.price_date <= position_date,
            )
            .order_by(MarketPrice.price_date.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="upsert_daily_snapshot")
    async def upsert_daily_snapshot(self, snapshot: DailyPositionSnapshot) -> DailyPositionSnapshot:
        try:
            insert_values = {
                "portfolio_id": snapshot.portfolio_id,
                "security_id": snapshot.security_id,
                "date": snapshot.date,
                "epoch": snapshot.epoch,
                "quantity": snapshot.quantity,
                "cost_basis": snapshot.cost_basis,
                "cost_basis_local": snapshot.cost_basis_local,
                "market_price": snapshot.market_price,
                "market_value": snapshot.market_value,
                "market_value_local": snapshot.market_value_local,
                "unrealized_gain_loss": snapshot.unrealized_gain_loss,
                "unrealized_gain_loss_local": snapshot.unrealized_gain_loss_local,
                "unrealized_price_gain_loss": snapshot.unrealized_price_gain_loss,
                "unrealized_fx_gain_loss": snapshot.unrealized_fx_gain_loss,
                "valuation_status": snapshot.valuation_status,
                "valuation_fx_rate_date": snapshot.valuation_fx_rate_date,
            }

            stmt = pg_insert(DailyPositionSnapshot).values(**insert_values)

            update_values = {
                "quantity": stmt.excluded.quantity,
                "cost_basis": stmt.excluded.cost_basis,
                "cost_basis_local": stmt.excluded.cost_basis_local,
                "market_price": stmt.excluded.market_price,
                "market_value": stmt.excluded.market_value,
                "market_value_local": stmt.excluded.market_value_local,
                "unrealized_gain_loss": stmt.excluded.unrealized_gain_loss,
                "unrealized_gain_loss_local": stmt.excluded.unrealized_gain_loss_local,
                "unrealized_price_gain_loss": stmt.excluded.unrealized_price_gain_loss,
                "unrealized_fx_gain_loss": stmt.excluded.unrealized_fx_gain_loss,
                "valuation_status": stmt.excluded.valuation_status,
                "valuation_fx_rate_date": stmt.excluded.valuation_fx_rate_date,
                "updated_at": func.now(),
            }

            final_stmt = stmt.on_conflict_do_update(
                index_elements=["portfolio_id", "security_id", "date", "epoch"], set_=update_values
            ).returning(DailyPositionSnapshot)

            result = await self.db.execute(final_stmt)
            persisted_snapshot = result.scalar_one()

            logger.info(
                "Staged upsert for daily snapshot for %s on %s",
                snapshot.security_id,
                snapshot.date,
            )
            return persisted_snapshot
        except Exception as exc:
            logger.error("Failed to stage upsert for daily snapshot: %s", exc, exc_info=True)
            raise

    @async_timed(repository="ValuationRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(self, max_attempts: int = 3) -> int:
        stale_rows = await self._find_stale_job_rows()
        if not stale_rows:
            return 0

        stale_job_groups = _classify_stale_valuation_jobs(stale_rows, max_attempts)
        await self._mark_superseded_stale_jobs(
            stale_job_groups.superseded_job_ids,
        )
        await self._mark_over_limit_stale_jobs_failed(
            stale_job_groups.failed_job_ids,
            max_attempts,
        )
        return await self._reset_retryable_stale_jobs(
            stale_job_groups.reset_job_ids,
        )

    async def _find_stale_job_rows(self) -> list[Any]:
        result = await self.db.execute(_stale_valuation_jobs_stmt(self))
        return result.all()

    async def _mark_superseded_stale_jobs(
        self,
        superseded_job_ids: list[int],
    ) -> None:
        normalized_job_ids = sorted(set(superseded_job_ids))
        if not normalized_job_ids:
            return
        observe_multi_statement_batch(
            operation=StatementBatchOperation.VALUATION_STALE_SUPERSEDED_UPDATE,
            item_count=len(normalized_job_ids),
            binds_per_row=1,
            reserved_binds=_STALE_SUPERSEDED_RESERVED_BINDS,
        )
        for job_id_chunk in iter_statement_chunks(
            normalized_job_ids,
            binds_per_row=1,
            reserved_binds=_STALE_SUPERSEDED_RESERVED_BINDS,
        ):
            await self.db.execute(_superseded_stale_jobs_update_stmt(list(job_id_chunk)))
        logger.warning(
            "Marked stale superseded valuation jobs as SKIPPED_SUPERSEDED.",
            extra={
                "event_name": "valuation_stale_recovery",
                "operation": "skip_superseded",
                "status": "staged",
                "reason_code": "newer_epoch_exists",
                "job_count": len(normalized_job_ids),
            },
        )

    async def _mark_over_limit_stale_jobs_failed(
        self,
        failed_job_ids: list[int],
        max_attempts: int,
    ) -> None:
        normalized_job_ids = sorted(set(failed_job_ids))
        if not normalized_job_ids:
            return
        observe_multi_statement_batch(
            operation=StatementBatchOperation.VALUATION_STALE_FAILED_UPDATE,
            item_count=len(normalized_job_ids),
            binds_per_row=1,
            reserved_binds=_STALE_FAILED_RESERVED_BINDS,
        )
        for job_id_chunk in iter_statement_chunks(
            normalized_job_ids,
            binds_per_row=1,
            reserved_binds=_STALE_FAILED_RESERVED_BINDS,
        ):
            await self.db.execute(_failed_stale_jobs_update_stmt(list(job_id_chunk)))
        logger.warning(
            "Marked stale valuation jobs as FAILED after max attempts.",
            extra={
                "event_name": "valuation_stale_recovery",
                "operation": "fail_over_limit",
                "status": "staged",
                "reason_code": "max_attempts_exceeded",
                "job_count": len(normalized_job_ids),
                "max_attempts": max_attempts,
            },
        )

    async def _reset_retryable_stale_jobs(
        self,
        reset_job_ids: list[int],
    ) -> int:
        normalized_job_ids = sorted(set(reset_job_ids))
        if not normalized_job_ids:
            return 0
        observe_multi_statement_batch(
            operation=StatementBatchOperation.VALUATION_STALE_RESET_UPDATE,
            item_count=len(normalized_job_ids),
            binds_per_row=1,
            reserved_binds=_STALE_RESET_RESERVED_BINDS,
        )
        reset_count = 0
        for job_id_chunk in iter_statement_chunks(
            normalized_job_ids,
            binds_per_row=1,
            reserved_binds=_STALE_RESET_RESERVED_BINDS,
        ):
            result = await self.db.execute(_reset_stale_jobs_update_stmt(list(job_id_chunk)))
            reset_count += len(result.fetchall())
        if reset_count > 0:
            logger.warning(
                "Reset %s stale valuation jobs from 'PROCESSING' to 'PENDING'.",
                reset_count,
            )
            self._observe_stale_resets(reset_count)
            self._observe_lease_transition("recovery", "reclaimed", reset_count)

        return reset_count

    @async_timed(repository="ValuationRepository", method="get_all_open_positions")
    async def get_all_open_positions(self) -> List[dict]:
        snapshot_security_id = func.trim(DailyPositionSnapshot.security_id)
        state_security_id = func.trim(PositionState.security_id)
        latest_snapshots_subq = (
            select(
                DailyPositionSnapshot.portfolio_id,
                snapshot_security_id.label("security_id"),
                DailyPositionSnapshot.quantity,
            )
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == DailyPositionSnapshot.portfolio_id,
                    state_security_id == snapshot_security_id,
                    PositionState.epoch == DailyPositionSnapshot.epoch,
                ),
            )
            .distinct(DailyPositionSnapshot.portfolio_id, snapshot_security_id)
            .order_by(
                DailyPositionSnapshot.portfolio_id,
                snapshot_security_id,
                DailyPositionSnapshot.date.desc(),
                DailyPositionSnapshot.id.desc(),
            )
            .subquery()
        )

        stmt = select(
            latest_snapshots_subq.c.portfolio_id, latest_snapshots_subq.c.security_id
        ).where(latest_snapshots_subq.c.quantity != 0)

        result = await self.db.execute(stmt)
        open_positions = result.mappings().all()
        logger.info("Found %s open positions across all portfolios.", len(open_positions))
        return open_positions

    @async_timed(repository="ValuationRepository", method="get_next_price_date")
    async def get_next_price_date(self, security_id: str, after_date: date) -> Optional[date]:
        normalized_security_id = normalize_lookup_identifier(security_id)
        market_price_security_id = func.trim(MarketPrice.security_id)
        stmt = (
            select(MarketPrice.price_date)
            .filter(
                market_price_security_id == normalized_security_id,
                MarketPrice.price_date > after_date,
            )
            .order_by(MarketPrice.price_date.asc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @async_timed(repository="ValuationRepository", method="get_first_open_dates_for_keys")
    async def get_first_open_dates_for_keys(
        self, keys: List[Tuple[str, str, int]]
    ) -> Dict[Tuple[str, str, int], date]:
        normalized_keys = sorted(set(keys))
        if not normalized_keys:
            return {}

        first_open_dates: Dict[Tuple[str, str, int], date] = {}
        observe_multi_statement_batch(
            operation=StatementBatchOperation.FIRST_OPEN_DATE_LOOKUP,
            item_count=len(normalized_keys),
            binds_per_row=3,
        )
        for key_chunk in iter_statement_chunks(normalized_keys, binds_per_row=3):
            stmt = (
                select(
                    PositionHistory.portfolio_id,
                    PositionHistory.security_id,
                    PositionHistory.epoch,
                    func.min(PositionHistory.position_date).label("first_open_date"),
                )
                .where(
                    tuple_(
                        PositionHistory.portfolio_id,
                        PositionHistory.security_id,
                        PositionHistory.epoch,
                    ).in_(key_chunk)
                )
                .group_by(
                    PositionHistory.portfolio_id,
                    PositionHistory.security_id,
                    PositionHistory.epoch,
                )
            )

            result = await self.db.execute(stmt)
            first_open_dates.update(
                {
                    (row.portfolio_id, row.security_id, row.epoch): row.first_open_date
                    for row in result
                }
            )
        return first_open_dates


@dataclass(frozen=True)
class _StaleValuationJobGroups:
    superseded_job_ids: list[int]
    failed_job_ids: list[int]
    reset_job_ids: list[int]


def _classify_stale_valuation_jobs(
    stale_rows: list[Any],
    max_attempts: int,
) -> _StaleValuationJobGroups:
    superseded_job_ids = _superseded_stale_job_ids(stale_rows)
    retryable_rows = _retryable_stale_rows(stale_rows, superseded_job_ids)
    return _StaleValuationJobGroups(
        superseded_job_ids=superseded_job_ids,
        failed_job_ids=_over_limit_stale_job_ids(retryable_rows, max_attempts),
        reset_job_ids=_resettable_stale_job_ids(retryable_rows, max_attempts),
    )


def _superseded_stale_job_ids(stale_rows: list[Any]) -> list[int]:
    return [row.id for row in stale_rows if _has_newer_epoch(row)]


def _retryable_stale_rows(stale_rows: list[Any], superseded_job_ids: list[int]) -> list[Any]:
    return [row for row in stale_rows if row.id not in superseded_job_ids]


def _over_limit_stale_job_ids(stale_rows: list[Any], max_attempts: int) -> list[int]:
    return [
        row.id
        for row in stale_rows
        if row.attempt_count >= max_attempts and not _requeue_requested(row)
    ]


def _resettable_stale_job_ids(stale_rows: list[Any], max_attempts: int) -> list[int]:
    return [
        row.id for row in stale_rows if row.attempt_count < max_attempts or _requeue_requested(row)
    ]


def _has_newer_epoch(stale_row: Any) -> bool:
    return bool(getattr(stale_row, "has_newer_epoch", False))


def _requeue_requested(stale_row: Any) -> bool:
    return getattr(stale_row, "requeue_requested", False) is True


def _stale_valuation_jobs_stmt(repository: ValuationRepositoryBase):
    newer_epoch = aliased(PortfolioValuationJob)
    return (
        select(
            PortfolioValuationJob.id,
            PortfolioValuationJob.attempt_count,
            PortfolioValuationJob.requeue_requested,
            PortfolioValuationJob.valuation_claim_token,
            repository._newer_epoch_exists(PortfolioValuationJob, newer_epoch).label(
                "has_newer_epoch"
            ),
        )
        .where(
            PortfolioValuationJob.status == "PROCESSING",
            PortfolioValuationJob.valuation_lease_expires_at <= func.clock_timestamp(),
        )
        .order_by(
            PortfolioValuationJob.valuation_lease_expires_at.asc(),
            PortfolioValuationJob.id.asc(),
        )
        .limit(POSTGRES_STATEMENT_ROW_LIMIT)
        .with_for_update(skip_locked=True)
    )


def _superseded_stale_jobs_update_stmt(
    superseded_job_ids: list[int],
):
    return (
        _stale_jobs_update_stmt(superseded_job_ids)
        .values(
            status="SKIPPED_SUPERSEDED",
            requeue_requested=False,
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
            failure_reason="Superseded by newer valuation epoch.",
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _failed_stale_jobs_update_stmt(
    failed_job_ids: list[int],
):
    return (
        _stale_jobs_update_stmt(failed_job_ids)
        .values(
            status="FAILED",
            requeue_requested=False,
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
            failure_reason="Expired valuation claim lease exceeded max attempts",
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _reset_stale_jobs_update_stmt(
    reset_job_ids: list[int],
):
    return (
        _stale_jobs_update_stmt(reset_job_ids)
        .values(
            status="PENDING",
            requeue_requested=False,
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
            updated_at=func.now(),
        )
        .returning(PortfolioValuationJob.id)
    )


def _stale_jobs_update_stmt(job_ids: list[int]):
    return update(PortfolioValuationJob).where(
        PortfolioValuationJob.id.in_(job_ids),
        PortfolioValuationJob.status == "PROCESSING",
        PortfolioValuationJob.valuation_lease_expires_at <= func.clock_timestamp(),
    )


def _dispatch_failed_valuation_jobs_update_stmt(
    *,
    job_claims: list[tuple[int, str]],
    max_attempts: int,
    failure_reason: str,
):
    return (
        _dispatch_recovery_valuation_jobs_update_stmt(job_claims)
        .where(
            PortfolioValuationJob.attempt_count >= max_attempts,
            PortfolioValuationJob.requeue_requested.is_(False),
        )
        .values(
            status="FAILED",
            requeue_requested=False,
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
            failure_reason=failure_reason,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _dispatch_retryable_valuation_jobs_update_stmt(
    *,
    job_claims: list[tuple[int, str]],
    max_attempts: int,
    failure_reason: str,
):
    return (
        _dispatch_recovery_valuation_jobs_update_stmt(job_claims)
        .where(
            or_(
                PortfolioValuationJob.attempt_count < max_attempts,
                PortfolioValuationJob.requeue_requested.is_(True),
            )
        )
        .values(
            status="PENDING",
            requeue_requested=False,
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
            failure_reason=failure_reason,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _dispatch_recovery_valuation_jobs_update_stmt(job_claims: list[tuple[int, str]]):
    return update(PortfolioValuationJob).where(
        tuple_(PortfolioValuationJob.id, PortfolioValuationJob.valuation_claim_token).in_(
            job_claims
        ),
        PortfolioValuationJob.status == "PROCESSING",
        PortfolioValuationJob.valuation_lease_expires_at > func.clock_timestamp(),
    )
