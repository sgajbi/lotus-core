# src/services/calculators/position_calculator/app/core/position_logic.py
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import List

from portfolio_common.config import KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC
from portfolio_common.database_models import PositionHistory
from portfolio_common.events import TransactionEvent, transaction_event_ordering_key
from portfolio_common.logging_utils import correlation_id_var, normalize_lineage_value
from portfolio_common.monitoring import REPROCESSING_EPOCH_BUMPED_TOTAL
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing import EpochFencer
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.position_models import PositionState as PositionStateDTO
from ..core.position_reducer import (
    PositionBalanceState,
    calculate_next_position_state,
    plan_backdated_replay,
)
from ..repositories.position_repository import PositionRepository

logger = logging.getLogger(__name__)


class PositionCalculator:
    """
    Handles position recalculation. Detects back-dated transactions and triggers
    a full reprocessing by incrementing the key's epoch and re-emitting all
    historical events for that key via the outbox pattern for atomicity.
    """

    @classmethod
    async def calculate(
        cls,
        event: TransactionEvent,
        db_session: AsyncSession,
        repo: PositionRepository,
        position_state_repo: PositionStateRepository,
        outbox_repo: OutboxRepository,
    ) -> None:
        """
        Orchestrates recalculation and reprocessing triggers for a single transaction event.
        """
        portfolio_id = event.portfolio_id
        security_id = event.security_id
        transaction_date = event.transaction_date.date()

        if not await cls._event_epoch_is_current(event, db_session):
            return

        current_state = await position_state_repo.get_or_create_state(portfolio_id, security_id)
        latest_position_history_date = await repo.get_latest_position_history_date(
            portfolio_id, security_id, current_state.epoch
        )
        latest_completed_snapshot_date = await repo.get_latest_completed_snapshot_date(
            portfolio_id, security_id, current_state.epoch
        )

        replay_decision = plan_backdated_replay(
            event_epoch=event.epoch,
            transaction_date=transaction_date,
            current_watermark_date=current_state.watermark_date,
            latest_position_history_date=latest_position_history_date,
            latest_completed_snapshot_date=latest_completed_snapshot_date,
        )
        if replay_decision.should_queue_replay:
            if replay_decision.replay_watermark_date is None:
                raise RuntimeError("Backdated replay decision did not include a replay watermark.")
            await cls._queue_backdated_replay(
                event=event,
                repo=repo,
                position_state_repo=position_state_repo,
                outbox_repo=outbox_repo,
                current_state=current_state,
                effective_completed_date=replay_decision.effective_completed_date,
                replay_watermark_date=replay_decision.replay_watermark_date,
                latest_position_history_date=latest_position_history_date,
            )
            return

        await cls._recalculate_position_history(
            event=event,
            repo=repo,
            position_state_repo=position_state_repo,
            current_state=current_state,
            transaction_date=transaction_date,
        )

    @staticmethod
    async def _event_epoch_is_current(event: TransactionEvent, db_session: AsyncSession) -> bool:
        fencer = EpochFencer(db_session, service_name="position-calculator")
        return await fencer.check(event)

    @classmethod
    async def _queue_backdated_replay(
        cls,
        *,
        event: TransactionEvent,
        repo: PositionRepository,
        position_state_repo: PositionStateRepository,
        outbox_repo: OutboxRepository,
        current_state,
        effective_completed_date: date,
        replay_watermark_date: date,
        latest_position_history_date: date | None,
    ) -> None:
        portfolio_id = event.portfolio_id
        security_id = event.security_id
        cls._log_backdated_replay_detected(
            event=event,
            current_state=current_state,
            effective_completed_date=effective_completed_date,
            latest_position_history_date=latest_position_history_date,
        )
        REPROCESSING_EPOCH_BUMPED_TOTAL.labels(trigger="backdated_transaction").inc()

        new_state = await position_state_repo.increment_epoch_and_reset_watermark(
            portfolio_id, security_id, current_state.epoch, replay_watermark_date
        )
        if new_state is None:
            cls._log_stale_backdated_replay(event, current_state.epoch)
            return

        events_to_replay = await cls._backdated_replay_events(event, repo)
        logger.info(
            "Atomically queuing "
            f"{len(events_to_replay)} events for reprocessing replay "
            f"in Epoch {new_state.epoch}"
        )
        await cls._publish_backdated_replay_events(
            events_to_replay=events_to_replay,
            outbox_repo=outbox_repo,
            replay_epoch=new_state.epoch,
        )

    @staticmethod
    def _log_backdated_replay_detected(
        *,
        event: TransactionEvent,
        current_state,
        effective_completed_date: date,
        latest_position_history_date: date | None,
    ) -> None:
        logger.warning(
            "Back-dated transaction detected. Triggering atomic reprocessing flow via outbox.",
            extra={
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "transaction_date": event.transaction_date.date().isoformat(),
                "effective_completed_date": effective_completed_date.isoformat(),
                "watermark_date": current_state.watermark_date.isoformat(),
                "latest_position_history_date": latest_position_history_date.isoformat()
                if latest_position_history_date
                else None,
                "current_epoch": current_state.epoch,
            },
        )

    @staticmethod
    def _log_stale_backdated_replay(event: TransactionEvent, expected_epoch: int) -> None:
        logger.warning(
            "Skipping back-dated replay because the epoch fence is stale.",
            extra={
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "expected_epoch": expected_epoch,
                "transaction_id": event.transaction_id,
            },
        )

    @staticmethod
    async def _backdated_replay_events(
        event: TransactionEvent, repo: PositionRepository
    ) -> list[TransactionEvent]:
        historical_db_txns = await repo.get_all_transactions_for_security(
            event.portfolio_id, event.security_id
        )
        events_to_replay = [TransactionEvent.model_validate(t) for t in historical_db_txns]
        if not any(
            historical_event.transaction_id == event.transaction_id
            for historical_event in events_to_replay
        ):
            events_to_replay.append(event)
        events_to_replay.sort(key=transaction_event_ordering_key)
        return events_to_replay

    @staticmethod
    async def _publish_backdated_replay_events(
        *,
        events_to_replay: list[TransactionEvent],
        outbox_repo: OutboxRepository,
        replay_epoch: int,
    ) -> None:
        replay_correlation_id = normalize_lineage_value(correlation_id_var.get())
        for event_to_publish in events_to_replay:
            event_to_publish.epoch = replay_epoch
            await outbox_repo.create_outbox_event(
                aggregate_type="ReprocessTransaction",
                aggregate_id=str(event_to_publish.portfolio_id),
                event_type="ReprocessTransactionReplay",
                topic=KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
                payload=event_to_publish.model_dump(mode="json"),
                correlation_id=replay_correlation_id,
            )

    @classmethod
    async def _recalculate_position_history(
        cls,
        *,
        event: TransactionEvent,
        repo: PositionRepository,
        position_state_repo: PositionStateRepository,
        current_state,
        transaction_date: date,
    ) -> None:
        portfolio_id = event.portfolio_id
        security_id = event.security_id
        message_epoch = event.epoch if event.epoch is not None else current_state.epoch
        await repo.acquire_position_history_replay_lock(portfolio_id, security_id, message_epoch)
        await repo.delete_positions_from(portfolio_id, security_id, transaction_date, message_epoch)
        anchor_position = await repo.get_last_position_before(
            portfolio_id, security_id, transaction_date, message_epoch
        )
        transactions_to_replay = await repo.get_transactions_on_or_after(
            portfolio_id, security_id, transaction_date
        )

        events_to_replay = [TransactionEvent.model_validate(t) for t in transactions_to_replay]
        new_positions = cls._calculate_new_positions(
            anchor_position, events_to_replay, message_epoch
        )

        await cls._save_positions_and_rearm_generation(
            new_positions=new_positions,
            position_state_repo=position_state_repo,
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_date=transaction_date,
            message_epoch=message_epoch,
            repo=repo,
        )
        logger.info(
            f"[Calculate] Staged {len(new_positions)} position records for Epoch {message_epoch}"
        )

    @staticmethod
    async def _save_positions_and_rearm_generation(
        *,
        new_positions: list[PositionHistory],
        position_state_repo: PositionStateRepository,
        portfolio_id: str,
        security_id: str,
        transaction_date: date,
        message_epoch: int,
        repo: PositionRepository,
    ) -> None:
        if not new_positions:
            return

        await repo.save_positions(new_positions)
        new_watermark_date = transaction_date - timedelta(days=1)
        updated_count = await position_state_repo.update_watermarks_if_older(
            keys=[(portfolio_id, security_id)],
            new_watermark_date=new_watermark_date,
            touch_if_already_lagging=True,
        )
        if updated_count:
            logger.info(
                "Re-armed valuation and timeseries generation after position history write.",
                extra={
                    "portfolio_id": portfolio_id,
                    "security_id": security_id,
                    "epoch": message_epoch,
                    "transaction_date": transaction_date.isoformat(),
                    "new_watermark_date": new_watermark_date.isoformat(),
                },
            )

    @staticmethod
    def _calculate_new_positions(
        anchor_position: PositionHistory | None, transactions: List[TransactionEvent], epoch: int
    ) -> List[PositionHistory]:
        if not transactions:
            return []

        current_state = PositionStateDTO(
            quantity=anchor_position.quantity if anchor_position else Decimal(0),
            cost_basis=anchor_position.cost_basis if anchor_position else Decimal(0),
            cost_basis_local=anchor_position.cost_basis_local
            if anchor_position and anchor_position.cost_basis_local is not None
            else Decimal(0),
        )

        new_history_records = []

        for transaction in transactions:
            new_state = PositionCalculator.calculate_next_position(current_state, transaction)

            new_position_record = PositionHistory(
                portfolio_id=transaction.portfolio_id,
                security_id=transaction.security_id,
                transaction_id=transaction.transaction_id,
                position_date=transaction.transaction_date.date(),
                quantity=new_state.quantity,
                cost_basis=new_state.cost_basis,
                cost_basis_local=new_state.cost_basis_local,
                epoch=epoch,
            )
            new_history_records.append(new_position_record)

            current_state = new_state

        return new_history_records

    @staticmethod
    def calculate_next_position(
        current_state: PositionStateDTO, transaction: TransactionEvent
    ) -> PositionStateDTO:
        next_state = calculate_next_position_state(
            PositionBalanceState(
                quantity=current_state.quantity,
                cost_basis=current_state.cost_basis,
                cost_basis_local=current_state.cost_basis_local,
            ),
            transaction,
        )
        return PositionStateDTO(
            quantity=next_state.quantity,
            cost_basis=next_state.cost_basis,
            cost_basis_local=next_state.cost_basis_local,
        )
