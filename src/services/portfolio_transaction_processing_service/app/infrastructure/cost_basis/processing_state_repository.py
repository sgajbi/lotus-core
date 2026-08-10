"""SQLAlchemy adapter for cost-basis serialization and replay checkpoints."""

import hashlib
import logging
from collections.abc import Callable
from time import monotonic
from typing import Protocol

from portfolio_common.database_models import CostBasisProcessingState
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.monitoring import (
    observe_cost_basis_processing_lock_wait,
    observe_linked_redemption_group_lock_wait,
)
from portfolio_common.utils import async_timed
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.postgresql.dml import Insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cost_basis import CostBasisProcessingCheckpoint

logger = logging.getLogger(__name__)


class LockWaitObserver(Protocol):
    """Observe one bounded advisory-lock wait outcome."""

    def __call__(self, *, outcome: str, seconds: float) -> None: ...


def cost_basis_processing_lock_key(portfolio_id: str, security_id: str) -> int:
    """Return the stable signed PostgreSQL advisory-lock key for one cost-basis stream."""

    normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
    normalized_security_id = normalize_lookup_identifier(security_id)
    lock_scope = f"cost-basis-processing:{normalized_portfolio_id}:{normalized_security_id}"
    digest = hashlib.blake2b(lock_scope.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


def linked_redemption_group_lock_key(
    portfolio_id: str,
    linked_transaction_group_id: str,
) -> int:
    """Return the stable advisory-lock key for one portfolio-owned redemption group."""

    normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
    normalized_group_id = normalize_lookup_identifier(linked_transaction_group_id)
    lock_scope = f"linked-redemption-group:{normalized_portfolio_id}:{normalized_group_id}"
    digest = hashlib.blake2b(lock_scope.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


class SqlAlchemyCostBasisProcessingStateRepository:
    """Serialize one cost-basis stream and persist its deterministic replay checkpoint."""

    def __init__(self, session: AsyncSession, *, clock: Callable[[], float] = monotonic) -> None:
        self._session = session
        self._clock = clock

    @async_timed(
        repository="CostBasisProcessingStateRepository",
        method="acquire_cost_basis_processing_lock",
    )
    async def acquire_cost_basis_processing_lock(
        self,
        portfolio_id: str,
        security_id: str,
    ) -> None:
        """Serialize state transitions for one normalized portfolio and security key."""

        await self._acquire_transaction_lock(
            lock_key=cost_basis_processing_lock_key(portfolio_id, security_id),
            lock_name="Cost-basis processing lock",
            wait_observer=observe_cost_basis_processing_lock_wait,
            log_context={
                "portfolio_id": normalize_lookup_identifier(portfolio_id),
                "security_id": normalize_lookup_identifier(security_id),
            },
        )

    @async_timed(
        repository="CostBasisProcessingStateRepository",
        method="acquire_linked_redemption_group_lock",
    )
    async def acquire_linked_redemption_group_lock(
        self,
        portfolio_id: str,
        linked_transaction_group_id: str,
    ) -> None:
        """Serialize linked-interest authority for one normalized portfolio and group."""

        await self._acquire_transaction_lock(
            lock_key=linked_redemption_group_lock_key(
                portfolio_id,
                linked_transaction_group_id,
            ),
            lock_name="Linked redemption group lock",
            wait_observer=observe_linked_redemption_group_lock_wait,
            log_context={
                "portfolio_id": normalize_lookup_identifier(portfolio_id),
                "linked_transaction_group_id": normalize_lookup_identifier(
                    linked_transaction_group_id
                ),
            },
        )

    async def _acquire_transaction_lock(
        self,
        *,
        lock_key: int,
        lock_name: str,
        wait_observer: LockWaitObserver,
        log_context: dict[str, str],
    ) -> None:
        """Acquire one advisory transaction lock with uniform telemetry and failure handling."""

        started_at = self._clock()
        try:
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)").bindparams(lock_key=lock_key)
            )
        except BaseException:
            wait_seconds = max(0.0, self._clock() - started_at)
            wait_observer(outcome="failed", seconds=wait_seconds)
            logger.warning(
                "%s acquisition failed.",
                lock_name,
                extra={**log_context, "lock_wait_seconds": wait_seconds},
                exc_info=True,
            )
            raise
        wait_seconds = max(0.0, self._clock() - started_at)
        wait_observer(outcome="acquired", seconds=wait_seconds)
        logger.debug(
            "%s acquired.",
            lock_name,
            extra={**log_context, "lock_wait_seconds": wait_seconds},
        )

    @async_timed(
        repository="CostBasisProcessingStateRepository",
        method="get_cost_basis_processing_checkpoint",
    )
    async def get_cost_basis_processing_checkpoint(
        self, *, portfolio_id: str, security_id: str
    ) -> CostBasisProcessingCheckpoint | None:
        """Load the durable ordering checkpoint for one cost-basis stream."""

        statement = select(CostBasisProcessingState).where(
            CostBasisProcessingState.portfolio_id == normalize_lookup_identifier(portfolio_id),
            CostBasisProcessingState.security_id == normalize_lookup_identifier(security_id),
        )
        row = (await self._session.execute(statement)).scalars().first()
        if row is None:
            return None
        return CostBasisProcessingCheckpoint(
            portfolio_id=row.portfolio_id,
            security_id=row.security_id,
            cost_basis_method=row.cost_basis_method,
            latest_transaction_date=row.latest_transaction_date,
            latest_dependency_rank=row.latest_dependency_rank,
            latest_cash_dependency_rank=row.latest_cash_dependency_rank,
            latest_child_sequence=row.latest_child_sequence,
            latest_target_instrument_id=row.latest_target_instrument_id,
            latest_quantity=row.latest_quantity,
            latest_transaction_id=row.latest_transaction_id,
            calculation_state_version=row.engine_state_version,
        )

    @async_timed(
        repository="CostBasisProcessingStateRepository",
        method="upsert_cost_basis_processing_checkpoint",
    )
    async def upsert_cost_basis_processing_checkpoint(
        self, checkpoint: CostBasisProcessingCheckpoint
    ) -> None:
        """Idempotently persist the latest deterministic ordering checkpoint."""

        await self._session.execute(cost_basis_processing_checkpoint_upsert_statement(checkpoint))


def cost_basis_processing_checkpoint_upsert_statement(
    checkpoint: CostBasisProcessingCheckpoint,
) -> Insert:
    """Build the canonical idempotent deterministic-checkpoint write."""

    payload = {
        "portfolio_id": checkpoint.portfolio_id,
        "security_id": checkpoint.security_id,
        "cost_basis_method": checkpoint.cost_basis_method,
        "latest_transaction_date": checkpoint.latest_transaction_date,
        "latest_dependency_rank": checkpoint.latest_dependency_rank,
        "latest_cash_dependency_rank": checkpoint.latest_cash_dependency_rank,
        "latest_child_sequence": checkpoint.latest_child_sequence,
        "latest_target_instrument_id": checkpoint.latest_target_instrument_id,
        "latest_quantity": checkpoint.latest_quantity,
        "latest_transaction_id": checkpoint.latest_transaction_id,
        "engine_state_version": checkpoint.calculation_state_version,
    }
    statement = pg_insert(CostBasisProcessingState).values(**payload)
    return statement.on_conflict_do_update(
        index_elements=["portfolio_id", "security_id"],
        set_={
            field_name: getattr(statement.excluded, field_name)
            for field_name in payload
            if field_name not in {"portfolio_id", "security_id"}
        },
    )
