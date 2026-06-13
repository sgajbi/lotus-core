# src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py
import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from confluent_kafka import Message
from portfolio_common.config import (
    KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC,
)
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    MarketPrice,
    Portfolio,
)
from portfolio_common.db import get_async_db_session
from portfolio_common.events import (
    DailyPositionSnapshotPersistedEvent,
    PortfolioValuationRequiredEvent,
)
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.monitoring import VALUATION_JOBS_FAILED_TOTAL, VALUATION_JOBS_SKIPPED_TOTAL
from portfolio_common.outbox_repository import OutboxRepository
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from ..logic.valuation_logic import ValuationLogic
from ..repositories.valuation_repository import ValuationRepository

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

    pass


@dataclass(frozen=True)
class _ValuationReferenceData:
    instrument: Instrument | None
    portfolio: Portfolio | None
    price: MarketPrice | None


@dataclass(frozen=True)
class _ValuationSnapshotResult:
    snapshot: DailyPositionSnapshot
    job_failure_reason: str | None


class ValuationConsumer(BaseConsumer):
    """
    Consumes scheduled valuation jobs, creates/updates the daily position snapshot,
    calculates market value, and saves the result.
    """

    @staticmethod
    def _build_processing_event_id(*, msg: Message) -> str:
        return f"{msg.topic()}-{msg.partition()}-{msg.offset()}"

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, OperationalError)),
        reraise=True,
    )
    async def process_message(self, msg: Message):
        key = msg.key().decode("utf-8") if msg.key() else "NoKey"
        value = msg.value().decode("utf-8")
        event_id = None
        event = None

        try:
            event_data = json.loads(value)
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ) as correlation_id:
                event = PortfolioValuationRequiredEvent.model_validate(event_data)
                event_id = self._build_processing_event_id(
                    msg=msg,
                )

                self._log_valuation_job_start(event)
                await self._process_valid_event(event, event_id, correlation_id)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                f"Message validation failed for key '{key}'. Sending to DLQ.", exc_info=True
            )
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, OperationalError) as e:
            logger.warning(
                f"DB or data availability error for event {event_id}: {e}. Retrying...",
                exc_info=False,
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error processing message with key '{key}'. Sending to DLQ.",
                exc_info=True,
            )
            if event:
                async for db in get_async_db_session():
                    async with db.begin():
                        repo = ValuationRepository(db)
                        await repo.update_job_status(
                            event.portfolio_id,
                            event.security_id,
                            event.valuation_date,
                            event.epoch,
                            status="FAILED",  # FIX: Use keyword argument for clarity
                            failure_reason=str(e),
                        )
            await self._send_to_dlq_async(msg, e)

    @staticmethod
    def _log_valuation_job_start(event: PortfolioValuationRequiredEvent) -> None:
        logger.info(
            "Processing valuation job for "
            f"{event.security_id} in {event.portfolio_id} "
            f"on {event.valuation_date} for epoch {event.epoch}"
        )

    async def _process_valid_event(
        self,
        event: PortfolioValuationRequiredEvent,
        event_id: str,
        correlation_id: str,
    ) -> None:
        async for db in get_async_db_session():
            try:
                await self._process_event_session(db, event, event_id, correlation_id)
            except DataNotFoundError as e:
                await self._mark_no_position_job_skipped(
                    db=db,
                    event=event,
                    event_id=event_id,
                    correlation_id=correlation_id,
                    error=e,
                )

    async def _process_event_session(
        self,
        db: Any,
        event: PortfolioValuationRequiredEvent,
        event_id: str,
        correlation_id: str,
    ) -> None:
        async with db.begin():
            idempotency_repo = IdempotencyRepository(db)
            outbox_repo = OutboxRepository(db)
            repo = ValuationRepository(db)

            if not await idempotency_repo.claim_event_processing(
                event_id,
                event.portfolio_id,
                SERVICE_NAME,
                correlation_id,
            ):
                logger.warning(f"Event {event_id} already processed. Skipping.")
                return

            snapshot_result = await self._build_snapshot_for_event(repo, event)
            if snapshot_result is None:
                return

            if not await self._complete_valuation_job(repo, event, snapshot_result):
                return

            await self._persist_and_publish_snapshot(
                repo=repo,
                outbox_repo=outbox_repo,
                snapshot=snapshot_result.snapshot,
                correlation_id=correlation_id,
            )

    @staticmethod
    async def _build_snapshot_for_event(
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
    ) -> _ValuationSnapshotResult | None:
        position_state = await ValuationConsumer._position_state_for_event(repo, event)
        reference_data = await ValuationConsumer._reference_data_for_event(repo, event)

        if not reference_data.instrument or not reference_data.portfolio:
            await ValuationConsumer._mark_missing_reference_data(repo, event, reference_data)
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

        return await ValuationConsumer._value_snapshot(
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
    ) -> _ValuationReferenceData:
        return _ValuationReferenceData(
            instrument=await repo.get_instrument(event.security_id),
            portfolio=await repo.get_portfolio(event.portfolio_id),
            price=await repo.get_latest_price_for_position(event.security_id, event.valuation_date),
        )

    @staticmethod
    async def _mark_missing_reference_data(
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        reference_data: _ValuationReferenceData,
    ) -> None:
        error_msg = ValuationConsumer._missing_reference_data_message(event, reference_data)
        VALUATION_JOBS_FAILED_TOTAL.labels(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            reason="missing_ref_data",
        ).inc()
        logger.error(f"{error_msg} Job will be marked FAILED.")
        if not await repo.update_job_status(
            event.portfolio_id,
            event.security_id,
            event.valuation_date,
            event.epoch,
            VALUATION_FAILED,
            failure_reason=error_msg,
        ):
            ValuationConsumer._log_lost_job_ownership(
                "Skipping valuation failure completion after losing job ownership.",
                event,
            )

    @staticmethod
    def _missing_reference_data_message(
        event: PortfolioValuationRequiredEvent,
        reference_data: _ValuationReferenceData,
    ) -> str:
        error_msg = "Missing critical data. "
        if not reference_data.instrument:
            error_msg += f"Instrument '{event.security_id}' not found. "
        if not reference_data.portfolio:
            error_msg += f"Portfolio '{event.portfolio_id}' not found."
        return error_msg

    @staticmethod
    async def _value_snapshot(
        *,
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        snapshot: DailyPositionSnapshot,
        instrument: Instrument,
        portfolio: Portfolio,
        price: MarketPrice | None,
    ) -> _ValuationSnapshotResult:
        if not price:
            snapshot.valuation_status = VALUATION_UNVALUED
            return _ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=None)

        instrument_currency = _normalize_currency_code(instrument.currency)
        portfolio_currency = _normalize_currency_code(portfolio.base_currency)
        price_currency = _normalize_currency_code(price.currency)
        fx_rate = await ValuationConsumer._instrument_to_portfolio_fx_rate(
            repo=repo,
            event=event,
            instrument_currency=instrument_currency,
            portfolio_currency=portfolio_currency,
        )

        if instrument_currency != portfolio_currency and not fx_rate:
            return ValuationConsumer._failed_missing_fx_snapshot(
                snapshot=snapshot,
                event=event,
                instrument_currency=instrument_currency,
                portfolio_currency=portfolio_currency,
            )

        valuation_result = ValuationLogic.calculate_valuation(
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
            ValuationConsumer._apply_valuation_result(snapshot, price, event, valuation_result)
            return _ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=None)

        snapshot.valuation_status = VALUATION_FAILED
        failure_reason = (
            f"Valuation logic returned no result for {event.security_id} on {event.valuation_date}"
        )
        VALUATION_JOBS_FAILED_TOTAL.labels(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            reason="valuation_logic_failed",
        ).inc()
        return _ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=failure_reason)

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

    @staticmethod
    def _failed_missing_fx_snapshot(
        *,
        snapshot: DailyPositionSnapshot,
        event: PortfolioValuationRequiredEvent,
        instrument_currency: str,
        portfolio_currency: str,
    ) -> _ValuationSnapshotResult:
        snapshot.valuation_status = VALUATION_FAILED
        failure_reason = (
            "Missing FX rate for "
            f"{instrument_currency}->{portfolio_currency} on or before {event.valuation_date}"
        )
        VALUATION_JOBS_FAILED_TOTAL.labels(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
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
        return _ValuationSnapshotResult(snapshot=snapshot, job_failure_reason=failure_reason)

    @staticmethod
    def _apply_valuation_result(
        snapshot: DailyPositionSnapshot,
        price: MarketPrice,
        event: PortfolioValuationRequiredEvent,
        valuation_result: tuple[Decimal, Decimal, Decimal, Decimal],
    ) -> None:
        snapshot.market_price = price.price
        (
            snapshot.market_value,
            snapshot.market_value_local,
            snapshot.unrealized_gain_loss,
            snapshot.unrealized_gain_loss_local,
        ) = valuation_result
        snapshot.valuation_status = (
            VALUATION_VALUED_CURRENT
            if price.price_date == event.valuation_date
            else VALUATION_VALUED_STALE
        )

    @staticmethod
    async def _complete_valuation_job(
        repo: ValuationRepository,
        event: PortfolioValuationRequiredEvent,
        snapshot_result: _ValuationSnapshotResult,
    ) -> bool:
        terminal_status = (
            VALUATION_FAILED
            if snapshot_result.snapshot.valuation_status in FAILED_JOB_STATUSES
            else VALUATION_JOB_COMPLETE
        )
        job_completed = cast(
            bool,
            await repo.update_job_status(
                event.portfolio_id,
                event.security_id,
                event.valuation_date,
                event.epoch,
                terminal_status,
                failure_reason=snapshot_result.job_failure_reason,
            ),
        )
        if not job_completed:
            ValuationConsumer._log_lost_job_ownership(
                "Skipping valuation completion side effects after losing job ownership.",
                event,
            )
        return job_completed

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
            event_type="DailyPositionSnapshotPersisted",
            topic=KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC,
            payload=completion_event.model_dump(mode="json"),
            correlation_id=correlation_id,
        )

    @staticmethod
    async def _mark_no_position_job_skipped(
        *,
        db,
        event: PortfolioValuationRequiredEvent,
        event_id: str,
        correlation_id: str,
        error: DataNotFoundError,
    ) -> None:
        VALUATION_JOBS_SKIPPED_TOTAL.labels(
            portfolio_id=event.portfolio_id, security_id=event.security_id
        ).inc()
        logger.warning(
            f"Skipping job due to missing position data: {error}",
            extra={
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "date": event.valuation_date,
            },
        )
        async with db.begin():
            repo = ValuationRepository(db)
            idempotency_repo = IdempotencyRepository(db)
            if not await repo.update_job_status(
                event.portfolio_id,
                event.security_id,
                event.valuation_date,
                event.epoch,
                status=VALUATION_JOB_SKIPPED_NO_POSITION,
                failure_reason=str(error),
            ):
                ValuationConsumer._log_lost_job_ownership(
                    "Skipping valuation no-position completion after losing job ownership.",
                    event,
                )
                return
            await idempotency_repo.mark_event_processed(
                event_id, event.portfolio_id, SERVICE_NAME, correlation_id
            )

    @staticmethod
    def _log_lost_job_ownership(message: str, event: PortfolioValuationRequiredEvent) -> None:
        logger.warning(
            message,
            extra={
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "valuation_date": str(event.valuation_date),
            },
        )
