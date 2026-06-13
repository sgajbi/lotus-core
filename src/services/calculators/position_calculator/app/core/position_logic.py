# src/services/calculators/position_calculator/app/core/position_logic.py
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, List

from portfolio_common.config import KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC
from portfolio_common.database_models import PositionHistory
from portfolio_common.decimal_amounts import required_decimal
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


CASH_POSITION_INFLOW_TRANSACTION_TYPES = {"DEPOSIT"}
CASH_POSITION_OUTFLOW_TRANSACTION_TYPES = {"WITHDRAWAL", "FEE", "TAX"}
CASH_POSITION_DELTA_TRANSACTION_TYPES = (
    CASH_POSITION_INFLOW_TRANSACTION_TYPES
    | CASH_POSITION_OUTFLOW_TRANSACTION_TYPES
    | {"ADJUSTMENT", "FX_CASH_SETTLEMENT_BUY", "FX_CASH_SETTLEMENT_SELL"}
)
POSITION_TRANSFER_TRANSACTION_TYPES = {
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
}
POSITION_TRANSFER_INFLOW_TRANSACTION_TYPES = {
    "TRANSFER_IN",
    "MERGER_IN",
    "EXCHANGE_IN",
    "REPLACEMENT_IN",
    "RIGHTS_ALLOCATE",
    "RIGHTS_SHARE_DELIVERY",
}
SAME_INSTRUMENT_CORPORATE_ACTION_TYPES = {
    "SPLIT",
    "REVERSE_SPLIT",
    "CONSOLIDATION",
    "BONUS_ISSUE",
    "STOCK_DIVIDEND",
}
SAME_INSTRUMENT_QUANTITY_DECREASE_TYPES = {"REVERSE_SPLIT", "CONSOLIDATION"}


def _normalize_position_code(value: object) -> str:
    return str(value or "").strip().upper()


_PositionUpdateHandler = Callable[[PositionStateDTO, TransactionEvent, str], PositionStateDTO]


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
                    topic=KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
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
            updated_count = await position_state_repo.update_watermarks_if_older(
                keys=[(portfolio_id, security_id)],
                new_watermark_date=transaction_date - timedelta(days=1),
            )
            if updated_count:
                logger.info(
                    "Re-armed valuation and timeseries generation after position history write.",
                    extra={
                        "portfolio_id": portfolio_id,
                        "security_id": security_id,
                        "epoch": message_epoch,
                        "transaction_date": transaction_date.isoformat(),
                        "new_watermark_date": (transaction_date - timedelta(days=1)).isoformat(),
                    },
                )

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
        txn_type = resolve_effective_processing_transaction_type(transaction)
        handler = PositionCalculator._position_update_handler(txn_type)
        next_state = (
            handler(current_state, transaction, txn_type)
            if handler is not None
            else PositionCalculator._unchanged_position_state(current_state, txn_type)
        )
        return PositionCalculator._zeroed_cost_basis_when_flat(next_state)

    @staticmethod
    def _position_update_handler(txn_type: str) -> _PositionUpdateHandler | None:
        if txn_type == "BUY":
            return PositionCalculator._buy_position_state

        elif txn_type in {"SELL", "CASH_IN_LIEU"}:
            return PositionCalculator._sell_position_state

        elif txn_type in CASH_POSITION_DELTA_TRANSACTION_TYPES:
            return PositionCalculator._cash_delta_position_state

        elif txn_type in POSITION_TRANSFER_TRANSACTION_TYPES:
            return PositionCalculator._transfer_position_state

        elif txn_type in SAME_INSTRUMENT_CORPORATE_ACTION_TYPES:
            return PositionCalculator._same_instrument_action_state

        elif txn_type in {"SPIN_OFF", "DEMERGER_OUT"}:
            return PositionCalculator._spin_off_position_state

        elif txn_type == "FX_CONTRACT_OPEN":
            return PositionCalculator._fx_contract_open_position_state

        elif txn_type == "FX_CONTRACT_CLOSE":
            return PositionCalculator._fx_contract_close_position_state

        return None

    @staticmethod
    def _unchanged_position_state(
        current_state: PositionStateDTO, txn_type: str
    ) -> PositionStateDTO:
        logger.debug(f"[CalculateNext] Txn type {txn_type} does not affect position quantity/cost.")
        return current_state

    @staticmethod
    def _position_state(
        quantity: Decimal, cost_basis: Decimal, cost_basis_local: Decimal
    ) -> PositionStateDTO:
        return PositionStateDTO(
            quantity=quantity,
            cost_basis=cost_basis,
            cost_basis_local=cost_basis_local,
        )

    @staticmethod
    def _buy_position_state(
        current_state: PositionStateDTO, transaction: TransactionEvent, _txn_type: str
    ) -> PositionStateDTO:
        return PositionCalculator._position_state(
            quantity=current_state.quantity + transaction.quantity,
            cost_basis=PositionCalculator._cost_basis_with_optional_net_cost(
                current_state.cost_basis, transaction.net_cost
            ),
            cost_basis_local=PositionCalculator._cost_basis_with_optional_net_cost(
                current_state.cost_basis_local, transaction.net_cost_local
            ),
        )

    @staticmethod
    def _sell_position_state(
        current_state: PositionStateDTO, transaction: TransactionEvent, _txn_type: str
    ) -> PositionStateDTO:
        return PositionCalculator._position_state(
            quantity=current_state.quantity - transaction.quantity,
            cost_basis=PositionCalculator._cost_basis_with_optional_net_cost(
                current_state.cost_basis, transaction.net_cost
            ),
            cost_basis_local=PositionCalculator._cost_basis_with_optional_net_cost(
                current_state.cost_basis_local, transaction.net_cost_local
            ),
        )

    @staticmethod
    def _cost_basis_with_optional_net_cost(
        current_cost_basis: Decimal, net_cost: Decimal | None
    ) -> Decimal:
        return current_cost_basis + net_cost if net_cost is not None else current_cost_basis

    @staticmethod
    def _cash_delta_position_state(
        current_state: PositionStateDTO, transaction: TransactionEvent, txn_type: str
    ) -> PositionStateDTO:
        quantity_delta, cost_basis_delta, cost_basis_local_delta = (
            PositionCalculator._cash_position_deltas(transaction, txn_type)
        )
        return PositionCalculator._position_state(
            quantity=current_state.quantity + quantity_delta,
            cost_basis=current_state.cost_basis + cost_basis_delta,
            cost_basis_local=current_state.cost_basis_local + cost_basis_local_delta,
        )

    @staticmethod
    def _transfer_position_state(
        current_state: PositionStateDTO, transaction: TransactionEvent, txn_type: str
    ) -> PositionStateDTO:
        transfer_quantity = transaction.quantity
        if transfer_quantity <= Decimal(0):
            logger.debug(
                "[CalculateNext] Txn type %s with zero transfer quantity treated as "
                "cash-only transfer and does not change security position quantity/cost.",
                txn_type,
            )
            return current_state

        is_inflow = txn_type in POSITION_TRANSFER_INFLOW_TRANSACTION_TYPES
        transfer_sign = Decimal(1) if is_inflow else Decimal(-1)
        return PositionCalculator._position_state(
            quantity=current_state.quantity + (transfer_sign * transfer_quantity),
            cost_basis=PositionCalculator._transfer_cost_basis(
                current_state.cost_basis,
                transaction.net_cost,
                transaction.gross_transaction_amount,
                is_inflow,
            ),
            cost_basis_local=PositionCalculator._transfer_cost_basis(
                current_state.cost_basis_local,
                transaction.net_cost_local,
                transaction.gross_transaction_amount,
                is_inflow,
            ),
        )

    @staticmethod
    def _transfer_cost_basis(
        current_cost_basis: Decimal,
        net_cost: Decimal | None,
        gross_transaction_amount: Decimal,
        is_inflow: bool,
    ) -> Decimal:
        if net_cost is not None:
            return current_cost_basis + net_cost
        if is_inflow:
            return current_cost_basis + gross_transaction_amount
        return current_cost_basis - gross_transaction_amount

    @staticmethod
    def _same_instrument_action_state(
        current_state: PositionStateDTO, transaction: TransactionEvent, txn_type: str
    ) -> PositionStateDTO:
        quantity_delta_sign = (
            Decimal(-1) if txn_type in SAME_INSTRUMENT_QUANTITY_DECREASE_TYPES else Decimal(1)
        )
        return PositionCalculator._quantity_delta_position_state(
            current_state, quantity_delta_sign * transaction.quantity
        )

    @staticmethod
    def _spin_off_position_state(
        current_state: PositionStateDTO, transaction: TransactionEvent, _txn_type: str
    ) -> PositionStateDTO:
        quantity_delta = -transaction.quantity if transaction.quantity > Decimal(0) else Decimal(0)
        return PositionCalculator._position_state(
            quantity=current_state.quantity + quantity_delta,
            cost_basis=PositionCalculator._spin_off_cost_basis(
                current_state.cost_basis,
                transaction.net_cost,
                transaction.gross_transaction_amount,
            ),
            cost_basis_local=PositionCalculator._spin_off_cost_basis(
                current_state.cost_basis_local,
                transaction.net_cost_local,
                transaction.gross_transaction_amount,
            ),
        )

    @staticmethod
    def _spin_off_cost_basis(
        current_cost_basis: Decimal,
        net_cost: Decimal | None,
        gross_transaction_amount: Decimal,
    ) -> Decimal:
        if net_cost is not None:
            return current_cost_basis + net_cost
        return current_cost_basis - gross_transaction_amount

    @staticmethod
    def _quantity_delta_position_state(
        current_state: PositionStateDTO, quantity_delta: Decimal
    ) -> PositionStateDTO:
        return PositionCalculator._position_state(
            quantity=current_state.quantity + quantity_delta,
            cost_basis=current_state.cost_basis,
            cost_basis_local=current_state.cost_basis_local,
        )

    @staticmethod
    def _fx_contract_open_position_state(
        current_state: PositionStateDTO, _transaction: TransactionEvent, _txn_type: str
    ) -> PositionStateDTO:
        return PositionCalculator._quantity_delta_position_state(current_state, Decimal(1))

    @staticmethod
    def _fx_contract_close_position_state(
        current_state: PositionStateDTO, _transaction: TransactionEvent, _txn_type: str
    ) -> PositionStateDTO:
        return PositionCalculator._quantity_delta_position_state(current_state, Decimal(-1))

    @staticmethod
    def _zeroed_cost_basis_when_flat(current_state: PositionStateDTO) -> PositionStateDTO:
        if not current_state.quantity.is_zero():
            return current_state
        return PositionCalculator._position_state(
            quantity=current_state.quantity,
            cost_basis=Decimal(0),
            cost_basis_local=Decimal(0),
        )

    @staticmethod
    def _cash_position_amount_delta(transaction: TransactionEvent, txn_type: str) -> Decimal:
        gross_amount = PositionCalculator._decimal_or_zero(
            transaction.gross_transaction_amount,
            field_name="gross_transaction_amount",
        )
        quantity_amount = PositionCalculator._decimal_or_zero(
            transaction.quantity,
            field_name="quantity",
        )
        magnitude = abs(gross_amount if not gross_amount.is_zero() else quantity_amount)
        if txn_type in CASH_POSITION_INFLOW_TRANSACTION_TYPES | {
            "ADJUSTMENT",
            "FX_CASH_SETTLEMENT_BUY",
        }:
            if txn_type == "ADJUSTMENT":
                movement_direction = _normalize_position_code(
                    transaction.movement_direction or "INFLOW"
                )
                return -magnitude if movement_direction == "OUTFLOW" else magnitude
            return magnitude
        return -magnitude

    @staticmethod
    def _cash_position_deltas(
        transaction: TransactionEvent, txn_type: str
    ) -> tuple[Decimal, Decimal, Decimal]:
        quantity_delta = PositionCalculator._cash_position_amount_delta(transaction, txn_type)
        use_quantity_fallback = txn_type == "ADJUSTMENT" or txn_type in (
            CASH_POSITION_INFLOW_TRANSACTION_TYPES | CASH_POSITION_OUTFLOW_TRANSACTION_TYPES
        )
        net_cost = PositionCalculator._optional_decimal(
            transaction.net_cost,
            field_name="net_cost",
        )
        net_cost_local = PositionCalculator._optional_decimal(
            transaction.net_cost_local,
            field_name="net_cost_local",
        )
        cost_basis_delta = (
            net_cost
            if net_cost is not None and not (use_quantity_fallback and net_cost == Decimal(0))
            else quantity_delta
        )
        cost_basis_local_delta = (
            net_cost_local
            if net_cost_local is not None
            and not (use_quantity_fallback and net_cost_local == Decimal(0))
            else quantity_delta
        )
        return quantity_delta, cost_basis_delta, cost_basis_local_delta

    @staticmethod
    def _decimal_or_zero(value: object, *, field_name: str) -> Decimal:
        if value is None or (isinstance(value, str) and not value.strip()):
            return Decimal(0)
        return Decimal(required_decimal(value, field_name=field_name))

    @staticmethod
    def _optional_decimal(value: object, *, field_name: str) -> Decimal | None:
        if value is None:
            return None
        return Decimal(required_decimal(value, field_name=field_name))
