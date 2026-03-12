# src/services/calculators/position_calculator/app/core/position_logic.py
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import List

from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
from portfolio_common.database_models import PositionHistory
from portfolio_common.events import TransactionEvent, transaction_event_ordering_key
from portfolio_common.logging_utils import correlation_id_var, normalize_lineage_value
from portfolio_common.monitoring import REPROCESSING_EPOCH_BUMPED_TOTAL
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing import EpochFencer
from portfolio_common.transaction_domain import resolve_effective_processing_transaction_type
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.position_models import PositionState as PositionStateDTO
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

        fencer = EpochFencer(db_session, service_name="position-calculator")
        if not await fencer.check(event):
            return

        current_state = await position_state_repo.get_or_create_state(portfolio_id, security_id)

        latest_snapshot_date = await repo.get_latest_completed_snapshot_date(
            portfolio_id, security_id, current_state.epoch
        )
        latest_position_history_date = await repo.get_latest_position_history_date(
            portfolio_id, security_id, current_state.epoch
        )
        effective_completed_date = max(
            current_state.watermark_date,
            latest_position_history_date if latest_position_history_date else date(1970, 1, 1),
            latest_snapshot_date if latest_snapshot_date else date(1970, 1, 1),
        )

        is_backdated = transaction_date < effective_completed_date

        if is_backdated and event.epoch is None:
            logger.warning(
                "Back-dated transaction detected. Triggering atomic reprocessing flow via outbox.",
                extra={
                    "portfolio_id": portfolio_id,
                    "security_id": security_id,
                    "transaction_date": transaction_date.isoformat(),
                    "effective_completed_date": effective_completed_date.isoformat(),
                    "watermark_date": current_state.watermark_date.isoformat(),
                    "latest_position_history_date": latest_position_history_date.isoformat()
                    if latest_position_history_date
                    else None,
                    "current_epoch": current_state.epoch,
                },
            )

            REPROCESSING_EPOCH_BUMPED_TOTAL.labels(
                portfolio_id=portfolio_id, security_id=security_id
            ).inc()

            new_watermark = transaction_date - timedelta(days=1)

            new_state = await position_state_repo.increment_epoch_and_reset_watermark(
                portfolio_id, security_id, current_state.epoch, new_watermark
            )
            if new_state is None:
                logger.warning(
                    "Skipping back-dated replay because the epoch fence is stale.",
                    extra={
                        "portfolio_id": portfolio_id,
                        "security_id": security_id,
                        "expected_epoch": current_state.epoch,
                        "transaction_id": event.transaction_id,
                    },
                )
                return

            historical_db_txns = await repo.get_all_transactions_for_security(
                portfolio_id, security_id
            )

            all_events_to_replay = [TransactionEvent.model_validate(t) for t in historical_db_txns]
            if not any(
                historical_event.transaction_id == event.transaction_id
                for historical_event in all_events_to_replay
            ):
                all_events_to_replay.append(event)
            # Ensure replay order is deterministic even when timestamps collide.
            all_events_to_replay.sort(key=transaction_event_ordering_key)

            logger.info(
                "Atomically queuing "
                f"{len(all_events_to_replay)} events for reprocessing replay "
                f"in Epoch {new_state.epoch}"
            )
            replay_correlation_id = normalize_lineage_value(correlation_id_var.get())
            for event_to_publish in all_events_to_replay:
                event_to_publish.epoch = new_state.epoch
                await outbox_repo.create_outbox_event(
                    aggregate_type="ReprocessTransaction",
                    aggregate_id=str(event_to_publish.portfolio_id),
                    event_type="ReprocessTransactionReplay",
                    topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                    payload=event_to_publish.model_dump(mode="json"),
                    correlation_id=replay_correlation_id,
                )
            return

        message_epoch = event.epoch if event.epoch is not None else current_state.epoch
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

        if new_positions:
            await repo.save_positions(new_positions)

        logger.info(
            f"[Calculate] Staged {len(new_positions)} position records for Epoch {message_epoch}"
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
        quantity = current_state.quantity
        cost_basis = current_state.cost_basis
        cost_basis_local = current_state.cost_basis_local
        txn_type = resolve_effective_processing_transaction_type(transaction)

        if txn_type == "BUY":
            quantity += transaction.quantity
            if transaction.net_cost is not None:
                cost_basis += transaction.net_cost
            if transaction.net_cost_local is not None:
                cost_basis_local += transaction.net_cost_local

        elif txn_type in {"SELL", "CASH_IN_LIEU"}:
            quantity -= transaction.quantity

            if transaction.net_cost is not None:
                cost_basis += transaction.net_cost
            if transaction.net_cost_local is not None:
                cost_basis_local += transaction.net_cost_local

        elif txn_type in ["DEPOSIT", "FEE", "TAX", "WITHDRAWAL"]:
            logger.debug(
                "[CalculateNext] Txn type %s is portfolio-level cashflow and does not "
                "change security position quantity/cost.",
                txn_type,
            )

        elif txn_type in [
            "TRANSFER_IN",
            "TRANSFER_OUT",
            "MERGER_IN",
            "MERGER_OUT",
            "EXCHANGE_IN",
            "EXCHANGE_OUT",
            "REPLACEMENT_IN",
            "REPLACEMENT_OUT",
            "SPIN_IN",
            "DEMERGER_IN",
            "RIGHTS_ALLOCATE",
            "RIGHTS_SHARE_DELIVERY",
            "RIGHTS_SUBSCRIBE",
            "RIGHTS_OVERSUBSCRIBE",
            "RIGHTS_SELL",
            "RIGHTS_EXPIRE",
        ]:
            transfer_quantity = transaction.quantity
            if transfer_quantity > 0:
                inflow_types = {
                    "TRANSFER_IN",
                    "MERGER_IN",
                    "EXCHANGE_IN",
                    "REPLACEMENT_IN",
                    "RIGHTS_ALLOCATE",
                    "RIGHTS_SHARE_DELIVERY",
                }
                transfer_sign = Decimal(1) if txn_type in inflow_types else Decimal(-1)
                quantity += transfer_sign * transfer_quantity

                if transaction.net_cost is not None:
                    cost_basis += transaction.net_cost
                elif txn_type in inflow_types:
                    cost_basis += transaction.gross_transaction_amount
                else:
                    cost_basis -= transaction.gross_transaction_amount

                if transaction.net_cost_local is not None:
                    cost_basis_local += transaction.net_cost_local
                elif txn_type in inflow_types:
                    cost_basis_local += transaction.gross_transaction_amount
                else:
                    cost_basis_local -= transaction.gross_transaction_amount
            else:
                logger.debug(
                    "[CalculateNext] Txn type %s with zero transfer quantity treated as "
                    "cash-only transfer and does not change security position quantity/cost.",
                    txn_type,
                )

        elif txn_type in {
            "SPLIT",
            "REVERSE_SPLIT",
            "CONSOLIDATION",
            "BONUS_ISSUE",
            "STOCK_DIVIDEND",
        }:
            # Same-instrument corporate actions: quantity changes, basis is preserved.
            quantity_delta_sign = (
                Decimal(-1) if txn_type in {"REVERSE_SPLIT", "CONSOLIDATION"} else Decimal(1)
            )
            quantity += quantity_delta_sign * transaction.quantity

        elif txn_type in {"SPIN_OFF", "DEMERGER_OUT"}:
            if transaction.quantity > Decimal(0):
                quantity -= transaction.quantity

            if transaction.net_cost is not None:
                cost_basis += transaction.net_cost
            else:
                cost_basis -= transaction.gross_transaction_amount

            if transaction.net_cost_local is not None:
                cost_basis_local += transaction.net_cost_local
            else:
                cost_basis_local -= transaction.gross_transaction_amount

        elif txn_type == "ADJUSTMENT":
            movement_direction = str(transaction.movement_direction or "INFLOW").upper()
            magnitude = abs(transaction.gross_transaction_amount)
            signed = -magnitude if movement_direction == "OUTFLOW" else magnitude
            quantity += signed
            cost_basis += signed
            cost_basis_local += signed

        elif txn_type == "FX_CASH_SETTLEMENT_BUY":
            signed = abs(transaction.gross_transaction_amount)
            quantity += signed
            cost_basis += signed
            cost_basis_local += signed

        elif txn_type == "FX_CASH_SETTLEMENT_SELL":
            signed = -abs(transaction.gross_transaction_amount)
            quantity += signed
            cost_basis += signed
            cost_basis_local += signed

        elif txn_type == "FX_CONTRACT_OPEN":
            quantity += Decimal(1)

        elif txn_type == "FX_CONTRACT_CLOSE":
            quantity -= Decimal(1)

        else:
            logger.debug(
                f"[CalculateNext] Txn type {txn_type} does not affect position quantity/cost."
            )

        if quantity.is_zero():
            cost_basis = Decimal(0)
            cost_basis_local = Decimal(0)

        return PositionStateDTO(
            quantity=quantity, cost_basis=cost_basis, cost_basis_local=cost_basis_local
        )
