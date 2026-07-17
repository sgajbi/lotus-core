"""Coordinate transitional position valuation workflow behavior."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from portfolio_common.config import KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    MarketPrice,
    Portfolio,
)
from portfolio_common.domain.eventing import portfolio_security_partition_key
from portfolio_common.events import (
    DailyPositionSnapshotPersistedEvent,
    PortfolioValuationRequiredEvent,
)
from portfolio_common.monitoring import VALUATION_JOBS_FAILED_TOTAL, VALUATION_JOBS_SKIPPED_TOTAL
from portfolio_common.valuation_job_contracts import ValuationJobTransitionOutcome

from .logic.valuation_logic import ValuationComponents, ValuationLogic

if TYPE_CHECKING:
    from portfolio_common.idempotency_repository import IdempotencyRepository
    from portfolio_common.outbox_repository import OutboxRepository

    from .repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-valuation-calculator"
FAILED_JOB_STATUSES = {"FAILED"}
VALUATION_FAILED = "FAILED"
VALUATION_UNVALUED = "UNVALUED"
VALUATION_VALUED_CURRENT = "VALUED_CURRENT"
VALUATION_VALUED_STALE = "VALUED_STALE"
VALUATION_JOB_COMPLETE = "COMPLETE"
VALUATION_JOB_SKIPPED_NO_POSITION = "SKIPPED_NO_POSITION"


def _normalize_currency_code(value: object) -> str:
    return str(value or "").strip().upper()


class DataNotFoundError(Exception):
    """Custom exception for retryable data fetching errors."""


@dataclass(frozen=True, slots=True)
class ValuationReferenceData:
    instrument: Instrument | None
    portfolio: Portfolio | None
    price: MarketPrice | None


@dataclass(frozen=True, slots=True)
class ValuationSnapshotResult:
    snapshot: DailyPositionSnapshot
    job_failure_reason: str | None


@dataclass(frozen=True, slots=True)
class ValuationProcessorDependencies:
    repo: ValuationRepository
    idempotency_repo: IdempotencyRepository
    outbox_repo: OutboxRepository


class ValuationProcessorDependencyFactory(Protocol):
    """Build valuation collaborators for one caller-owned database session."""

    def from_session(self, db: Any) -> ValuationProcessorDependencies: ...


class ValuationJobProcessor:
    def __init__(
        self,
        *,
        session_provider: Callable[[], Any],
        dependency_factory: ValuationProcessorDependencyFactory,
    ) -> None:
        self._session_provider = session_provider
        self._dependency_factory = dependency_factory

    async def process_valid_event(
        self,
        event: PortfolioValuationRequiredEvent,
        event_id: str,
        correlation_id: str,
    ) -> None:
        async for db in self._session_provider():
            try:
                await self._process_event_session(db, event, event_id, correlation_id)
            except DataNotFoundError as exc:
                await self._mark_no_position_job_skipped(
                    db=db,
                    event=event,
                    event_id=event_id,
                    correlation_id=correlation_id,
                    error=exc,
                )

    async def _process_event_session(
        self,
        db: Any,
        event: PortfolioValuationRequiredEvent,
        event_id: str,
        correlation_id: str,
    ) -> None:
        async with db.begin():
            dependencies = self._dependency_factory.from_session(db)

            if not await dependencies.idempotency_repo.claim_event_processing(
                event_id,
                event.portfolio_id,
                SERVICE_NAME,
                correlation_id,
            ):
                logger.warning("Event %s already processed. Skipping.", event_id)
                return

            snapshot_result = await self._build_snapshot_for_event(dependencies.repo, event)
            if snapshot_result is None:
                return

            if not await self._complete_valuation_job(dependencies.repo, event, snapshot_result):
                return

            await self._persist_and_publish_snapshot(
                repo=dependencies.repo,
                outbox_repo=dependencies.outbox_repo,
                snapshot=snapshot_result.snapshot,
                correlation_id=correlation_id,
            )

    async def mark_failed_after_unexpected_error(
        self,
        event: PortfolioValuationRequiredEvent,
        exc: Exception,
    ) -> None:
        async for db in self._session_provider():
            async with db.begin():
                dependencies = self._dependency_factory.from_session(db)
                outcome = await dependencies.repo.update_job_status(
                    event.portfolio_id,
                    event.security_id,
                    event.valuation_date,
                    event.epoch,
                    status=VALUATION_FAILED,
                    failure_reason=str(exc),
                )
                self._terminal_transition_applied(
                    outcome,
                    event,
                    side_effect_name="valuation failure transition",
                )

    async def _build_snapshot_for_event(
        self,
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
    ) -> ValuationSnapshotResult | None:
        position_state = await self._position_state_for_event(repo, event)
        reference_data = await self._reference_data_for_event(repo, event)

        if not reference_data.instrument or not reference_data.portfolio:
            await self._mark_missing_reference_data(repo, event, reference_data)
            return None

        snapshot = DailyPositionSnapshot(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            date=event.valuation_date,
            epoch=event.epoch,
            quantity=position_state.quantity,
            cost_basis=position_state.cost_basis,
            cost_basis_local=position_state.cost_basis_local,
        )

        return await self._value_snapshot(
            repo=repo,
            event=event,
            snapshot=snapshot,
            instrument=reference_data.instrument,
            portfolio=reference_data.portfolio,
            price=reference_data.price,
        )

    @staticmethod
    async def _position_state_for_event(
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
    ):
        position_state = await repo.get_last_position_history_before_date(
            event.portfolio_id,
            event.security_id,
            event.valuation_date,
            event.epoch,
        )
        if position_state:
            return position_state
        raise DataNotFoundError(
            "Position history not found for "
            f"epoch {event.epoch} of {event.security_id} "
            f"on or before {event.valuation_date}"
        )

    @staticmethod
    async def _reference_data_for_event(
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
    ) -> ValuationReferenceData:
        return ValuationReferenceData(
            instrument=await repo.get_instrument(event.security_id),
            portfolio=await repo.get_portfolio(event.portfolio_id),
            price=await repo.get_latest_price_for_position(event.security_id, event.valuation_date),
        )

    async def _mark_missing_reference_data(
        self,
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        reference_data: ValuationReferenceData,
    ) -> None:
        error_msg = self._missing_reference_data_message(event, reference_data)
        VALUATION_JOBS_FAILED_TOTAL.labels(
            reason="missing_ref_data",
        ).inc()
        logger.error("%s Job will be marked FAILED.", error_msg)
        outcome = await repo.update_job_status(
            event.portfolio_id,
            event.security_id,
            event.valuation_date,
            event.epoch,
            VALUATION_FAILED,
            failure_reason=error_msg,
        )
        self._terminal_transition_applied(
            outcome,
            event,
            side_effect_name="valuation failure completion",
        )

    @staticmethod
    def _missing_reference_data_message(
        event: PortfolioValuationRequiredEvent,
        reference_data: ValuationReferenceData,
    ) -> str:
        error_msg = "Missing critical data. "
        if not reference_data.instrument:
            error_msg += f"Instrument '{event.security_id}' not found. "
        if not reference_data.portfolio:
            error_msg += f"Portfolio '{event.portfolio_id}' not found."
        return error_msg

    async def _value_snapshot(
        self,
        *,
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        snapshot: DailyPositionSnapshot,
        instrument: Instrument,
        portfolio: Portfolio,
        price: MarketPrice | None,
    ) -> ValuationSnapshotResult:
        if not price:
            snapshot.valuation_status = VALUATION_UNVALUED
            return ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=None)

        instrument_currency = _normalize_currency_code(instrument.currency)
        portfolio_currency = _normalize_currency_code(portfolio.base_currency)
        price_currency = _normalize_currency_code(price.currency)
        fx_rate = await self._instrument_to_portfolio_fx_rate(
            repo=repo,
            event=event,
            instrument_currency=instrument_currency,
            portfolio_currency=portfolio_currency,
        )

        if instrument_currency != portfolio_currency and not fx_rate:
            return self._failed_missing_fx_snapshot(
                snapshot=snapshot,
                event=event,
                instrument_currency=instrument_currency,
                portfolio_currency=portfolio_currency,
            )

        valuation_result = ValuationLogic.calculate_valuation_components(
            quantity=snapshot.quantity,
            market_price=price.price,
            cost_basis_base=snapshot.cost_basis,
            cost_basis_local=snapshot.cost_basis_local,
            price_currency=price_currency,
            instrument_currency=instrument_currency,
            portfolio_currency=portfolio_currency,
            product_type=instrument.product_type,
            price_to_instrument_fx_rate=None,
            instrument_to_portfolio_fx_rate=fx_rate.rate if fx_rate else None,
        )
        if valuation_result:
            self._apply_valuation_result(snapshot, price, event, valuation_result)
            return ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=None)

        snapshot.valuation_status = VALUATION_FAILED
        failure_reason = (
            f"Valuation logic returned no result for {event.security_id} on {event.valuation_date}"
        )
        VALUATION_JOBS_FAILED_TOTAL.labels(
            reason="valuation_logic_failed",
        ).inc()
        return ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=failure_reason)

    @staticmethod
    async def _instrument_to_portfolio_fx_rate(
        *,
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        instrument_currency: str,
        portfolio_currency: str,
    ) -> FxRate | None:
        if instrument_currency == portfolio_currency:
            return None
        return await repo.get_fx_rate(
            instrument_currency,
            portfolio_currency,
            event.valuation_date,
        )

    def _failed_missing_fx_snapshot(
        self,
        *,
        snapshot: DailyPositionSnapshot,
        event: PortfolioValuationRequiredEvent,
        instrument_currency: str,
        portfolio_currency: str,
    ) -> ValuationSnapshotResult:
        snapshot.valuation_status = VALUATION_FAILED
        failure_reason = (
            "Missing FX rate for "
            f"{instrument_currency}->{portfolio_currency} on or before {event.valuation_date}"
        )
        VALUATION_JOBS_FAILED_TOTAL.labels(
            reason="missing_fx_rate",
        ).inc()
        logger.error(
            "Missing required FX rate for valuation. Job will be marked FAILED.",
            extra={
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "valuation_date": str(event.valuation_date),
            },
        )
        return ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=failure_reason)

    @staticmethod
    def _apply_valuation_result(
        snapshot: DailyPositionSnapshot,
        price: MarketPrice,
        event: PortfolioValuationRequiredEvent,
        valuation_result: ValuationComponents,
    ) -> None:
        snapshot.market_price = price.price
        snapshot.market_value = valuation_result.market_value_base
        snapshot.market_value_local = valuation_result.market_value_local
        snapshot.unrealized_gain_loss = valuation_result.unrealized_total_base
        snapshot.unrealized_gain_loss_local = valuation_result.unrealized_total_local
        snapshot.unrealized_price_gain_loss = valuation_result.unrealized_price_base
        snapshot.unrealized_fx_gain_loss = valuation_result.unrealized_fx_base
        snapshot.valuation_status = (
            VALUATION_VALUED_CURRENT
            if price.price_date == event.valuation_date
            else VALUATION_VALUED_STALE
        )

    async def _complete_valuation_job(
        self,
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        snapshot_result: ValuationSnapshotResult,
    ) -> bool:
        terminal_status = (
            VALUATION_FAILED
            if snapshot_result.snapshot.valuation_status in FAILED_JOB_STATUSES
            else VALUATION_JOB_COMPLETE
        )
        outcome = await repo.update_job_status(
            event.portfolio_id,
            event.security_id,
            event.valuation_date,
            event.epoch,
            terminal_status,
            failure_reason=snapshot_result.job_failure_reason,
        )
        return self._terminal_transition_applied(
            outcome,
            event,
            side_effect_name="valuation completion side effects",
        )

    @staticmethod
    async def _persist_and_publish_snapshot(
        *,
        repo: ValuationRepository,
        outbox_repo: OutboxRepository,
        snapshot: DailyPositionSnapshot,
        correlation_id: str,
    ) -> None:
        persisted_snapshot = await repo.upsert_daily_snapshot(snapshot)
        completion_event = DailyPositionSnapshotPersistedEvent.model_validate(persisted_snapshot)

        await outbox_repo.create_outbox_event(
            aggregate_type="DailyPositionSnapshot",
            aggregate_id=persisted_snapshot.portfolio_id,
            partition_key=portfolio_security_partition_key(
                persisted_snapshot.portfolio_id,
                persisted_snapshot.security_id,
            ),
            event_type="DailyPositionSnapshotPersisted",
            topic=KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC,
            payload=completion_event.model_dump(mode="json"),
            correlation_id=correlation_id,
        )

    async def _mark_no_position_job_skipped(
        self,
        *,
        db: Any,
        event: PortfolioValuationRequiredEvent,
        event_id: str,
        correlation_id: str,
        error: DataNotFoundError,
    ) -> None:
        VALUATION_JOBS_SKIPPED_TOTAL.labels(reason="no_position_history").inc()
        logger.warning(
            "Skipping job due to missing position data: %s",
            error,
            extra={
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "date": event.valuation_date,
            },
        )
        async with db.begin():
            dependencies = self._dependency_factory.from_session(db)
            outcome = await dependencies.repo.update_job_status(
                event.portfolio_id,
                event.security_id,
                event.valuation_date,
                event.epoch,
                status=VALUATION_JOB_SKIPPED_NO_POSITION,
                failure_reason=str(error),
            )
            if not self._terminal_transition_applied(
                outcome,
                event,
                side_effect_name="valuation no-position completion",
            ):
                return
            await dependencies.idempotency_repo.mark_event_processed(
                event_id, event.portfolio_id, SERVICE_NAME, correlation_id
            )

    @staticmethod
    def _terminal_transition_applied(
        outcome: ValuationJobTransitionOutcome,
        event: PortfolioValuationRequiredEvent,
        *,
        side_effect_name: str,
    ) -> bool:
        if outcome is ValuationJobTransitionOutcome.TERMINAL_APPLIED:
            return True
        reason = (
            "newer source work requested requeue"
            if outcome is ValuationJobTransitionOutcome.REQUEUED
            else "job ownership was lost"
        )
        logger.warning(
            "Skipping %s because %s.",
            side_effect_name,
            reason,
            extra={
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "valuation_date": str(event.valuation_date),
                "transition_outcome": outcome.value,
            },
        )
        return False
