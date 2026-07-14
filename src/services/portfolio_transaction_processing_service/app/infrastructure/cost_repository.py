"""SQLAlchemy persistence for transaction cost-basis processing."""

from decimal import Decimal
from typing import Any

from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    PositionLotState,
    TransactionCost,
)
from portfolio_common.database_models import (
    Transaction as DBTransaction,
)
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.events import TransactionEvent, event_business_payload
from portfolio_common.identifiers import normalize_lookup_identifier
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.cost_basis import (
    CostBasisTransaction as EngineTransaction,
)
from ..domain.cost_basis import OpenLotState
from ..domain.transaction import BookedTransaction
from ..ports import OpenLotCheckpointRecord
from .booked_transaction_event_mapper import to_booked_transaction
from .cost_basis.lot_state_mapper import buy_lot_state_payload, mutable_lot_state_fields

TRANSACTION_METADATA_FIELDS = (
    "economic_event_id",
    "linked_transaction_group_id",
    "calculation_policy_id",
    "calculation_policy_version",
    "source_system",
    "cash_entry_mode",
    "external_cash_transaction_id",
    "settlement_cash_account_id",
    "settlement_cash_instrument_id",
    "movement_direction",
    "originating_transaction_id",
    "originating_transaction_type",
    "adjustment_reason",
    "link_type",
    "reconciliation_key",
    "interest_direction",
    "withholding_tax_amount",
    "other_interest_deductions_amount",
    "net_interest_amount",
    "component_type",
    "component_id",
    "linked_component_ids",
    "fx_cash_leg_role",
    "linked_fx_cash_leg_id",
    "settlement_status",
    "pair_base_currency",
    "pair_quote_currency",
    "fx_rate_quote_convention",
    "buy_currency",
    "sell_currency",
    "buy_amount",
    "sell_amount",
    "contract_rate",
    "fx_contract_id",
    "fx_contract_open_transaction_id",
    "fx_contract_close_transaction_id",
    "settlement_of_fx_contract_id",
    "swap_event_id",
    "near_leg_group_id",
    "far_leg_group_id",
    "spot_exposure_model",
    "fx_realized_pnl_mode",
    "allocated_cost_basis_local",
    "allocated_cost_basis_base",
    "realized_capital_pnl_local",
    "realized_fx_pnl_local",
    "realized_total_pnl_local",
    "realized_capital_pnl_base",
    "realized_fx_pnl_base",
    "realized_total_pnl_base",
    "parent_transaction_reference",
    "linked_parent_event_id",
    "parent_event_reference",
    "child_role",
    "child_sequence_hint",
    "dependency_reference_ids",
    "source_instrument_id",
    "target_instrument_id",
    "source_transaction_reference",
    "target_transaction_reference",
    "linked_cash_transaction_id",
    "has_synthetic_flow",
    "synthetic_flow_effective_date",
    "synthetic_flow_amount_local",
    "synthetic_flow_currency",
    "synthetic_flow_amount_base",
    "synthetic_flow_fx_rate_to_base",
    "synthetic_flow_price_used",
    "synthetic_flow_quantity_used",
    "synthetic_flow_valuation_method",
    "synthetic_flow_classification",
    "synthetic_flow_price_source",
    "synthetic_flow_fx_source",
    "synthetic_flow_source",
)

TRANSACTION_TABLE_FIELDS = frozenset(DBTransaction.__table__.columns.keys())
TRANSACTION_EVENT_PERSISTENCE_EXCLUDE_FIELDS = frozenset(
    {"id", "epoch", "brokerage", "stamp_duty", "exchange_fee", "gst", "other_fees"}
)


def _transaction_event_payload(event: TransactionEvent) -> dict[str, Any]:
    event_payload = event_business_payload(event, mode="python")
    return {
        field: value
        for field, value in event_payload.items()
        if value is not None
        and field in TRANSACTION_TABLE_FIELDS
        and field not in TRANSACTION_EVENT_PERSISTENCE_EXCLUDE_FIELDS
    }


FEE_COMPONENT_FIELDS = (
    "brokerage",
    "stamp_duty",
    "exchange_fee",
    "gst",
    "other_fees",
)


def _positive_fee_components(fees: object | None) -> dict[str, Decimal]:
    if fees is None:
        return {}
    return {
        field_name: amount
        for field_name in FEE_COMPONENT_FIELDS
        if (amount := getattr(fees, field_name, None) or Decimal(0)) > 0
    }


def _transaction_cost_rows(
    *,
    transaction_result: EngineTransaction,
    db_txn: DBTransaction,
) -> list[TransactionCost]:
    currency = normalize_currency_code(db_txn.trade_currency or db_txn.currency)
    return [
        TransactionCost(
            transaction_id=transaction_result.transaction_id,
            fee_type=fee_type,
            amount=amount,
            currency=currency,
        )
        for fee_type, amount in _positive_fee_components(transaction_result.fees).items()
    ]


class CostCalculatorRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_transaction_history(
        self, portfolio_id: str, security_id: str, exclude_id: str | None = None
    ) -> list[BookedTransaction]:
        """
        Fetches all transactions for a given security in a portfolio,
        optionally excluding one by its transaction_id.
        """
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = select(DBTransaction).where(
            func.trim(DBTransaction.portfolio_id) == normalized_portfolio_id,
            func.trim(DBTransaction.security_id) == normalized_security_id,
        )

        if exclude_id:
            normalized_exclude_id = normalize_lookup_identifier(exclude_id)
            stmt = stmt.where(func.trim(DBTransaction.transaction_id) != normalized_exclude_id)

        stmt = stmt.order_by(
            DBTransaction.transaction_date.asc(),
            DBTransaction.transaction_id.asc(),
        )

        result = await self.db.execute(stmt)
        return [
            to_booked_transaction(TransactionEvent.model_validate(row))
            for row in result.scalars().all()
        ]

    async def get_open_lot_checkpoint_records(
        self, *, portfolio_id: str, security_id: str
    ) -> list[OpenLotCheckpointRecord]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = (
            select(PositionLotState, DBTransaction)
            .join(
                DBTransaction,
                DBTransaction.transaction_id == PositionLotState.source_transaction_id,
            )
            .where(
                func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionLotState.security_id) == normalized_security_id,
                func.trim(DBTransaction.portfolio_id) == normalized_portfolio_id,
                func.trim(DBTransaction.security_id) == normalized_security_id,
                PositionLotState.open_quantity > Decimal(0),
            )
            .order_by(
                DBTransaction.transaction_date.asc(),
                DBTransaction.quantity.desc(),
                DBTransaction.transaction_id.asc(),
            )
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            OpenLotCheckpointRecord(
                transaction=to_booked_transaction(TransactionEvent.model_validate(transaction)),
                quantity=lot.open_quantity,
                cost_local=lot.lot_cost_local,
                cost_base=lot.lot_cost_base,
            )
            for lot, transaction in rows
        ]

    async def get_fifo_disposal_lot_checkpoint_records(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        required_quantity: Decimal,
    ) -> list[OpenLotCheckpointRecord]:
        """Stream the oldest open lots needed to cover one FIFO disposal."""
        if required_quantity <= Decimal(0):
            raise ValueError("FIFO disposal checkpoint quantity must be positive")

        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = (
            select(PositionLotState, DBTransaction)
            .join(
                DBTransaction,
                DBTransaction.transaction_id == PositionLotState.source_transaction_id,
            )
            .where(
                func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionLotState.security_id) == normalized_security_id,
                func.trim(DBTransaction.portfolio_id) == normalized_portfolio_id,
                func.trim(DBTransaction.security_id) == normalized_security_id,
                PositionLotState.open_quantity > Decimal(0),
            )
            .order_by(
                DBTransaction.transaction_date.asc(),
                DBTransaction.quantity.desc(),
                DBTransaction.transaction_id.asc(),
            )
            .execution_options(yield_per=64)
        )

        records: list[OpenLotCheckpointRecord] = []
        covered_quantity = Decimal(0)
        result = await self.db.stream(stmt)
        try:
            async for lot, transaction in result:
                records.append(
                    OpenLotCheckpointRecord(
                        transaction=to_booked_transaction(
                            TransactionEvent.model_validate(transaction)
                        ),
                        quantity=lot.open_quantity,
                        cost_local=lot.lot_cost_local,
                        cost_base=lot.lot_cost_base,
                    )
                )
                covered_quantity += lot.open_quantity
                if covered_quantity >= required_quantity:
                    break
        finally:
            await result.close()
        return records

    async def apply_transaction_costs(
        self, transaction_result: EngineTransaction
    ) -> BookedTransaction | None:
        """Apply calculated costs and return the updated canonical domain transaction."""
        stmt = select(DBTransaction).filter_by(transaction_id=transaction_result.transaction_id)
        result = await self.db.execute(stmt)
        db_txn_to_update = result.scalars().first()

        if db_txn_to_update:
            db_txn_to_update.net_cost = transaction_result.net_cost
            db_txn_to_update.gross_cost = transaction_result.gross_cost
            db_txn_to_update.realized_gain_loss = transaction_result.realized_gain_loss
            db_txn_to_update.transaction_fx_rate = transaction_result.transaction_fx_rate
            db_txn_to_update.net_cost_local = transaction_result.net_cost_local
            db_txn_to_update.realized_gain_loss_local = transaction_result.realized_gain_loss_local
            for field_name in TRANSACTION_METADATA_FIELDS:
                field_value = getattr(transaction_result, field_name, None)
                if field_value is not None:
                    setattr(db_txn_to_update, field_name, field_value)

        if db_txn_to_update is None:
            return None
        return to_booked_transaction(TransactionEvent.model_validate(db_txn_to_update))

    async def get_booked_transaction(
        self, transaction_id: str, *, portfolio_id: str | None = None
    ) -> BookedTransaction | None:
        """Load one persisted transaction as an immutable domain transaction."""

        stmt = select(DBTransaction).where(DBTransaction.transaction_id == transaction_id)
        if portfolio_id:
            stmt = stmt.where(DBTransaction.portfolio_id == portfolio_id)
        result = await self.db.execute(stmt)
        transaction = result.scalars().first()
        if transaction is None:
            return None
        return to_booked_transaction(TransactionEvent.model_validate(transaction))

    async def upsert_transaction_event(self, event: TransactionEvent) -> None:
        """Upsert one transaction event without exposing its persistence representation."""

        event_dict = _transaction_event_payload(event)
        stmt = pg_insert(DBTransaction).values(**event_dict)
        update_fields = [k for k in event_dict.keys() if k not in {"id", "transaction_id"}]
        update_dict = {field: getattr(stmt.excluded, field) for field in update_fields}
        await self.db.execute(
            stmt.on_conflict_do_update(index_elements=["transaction_id"], set_=update_dict)
        )

    async def replace_transaction_cost_breakdown(
        self, transaction_result: EngineTransaction
    ) -> None:
        """
        Replaces the per-fee breakdown rows for a transaction.

        The method is idempotent for reprocessing because existing rows are deleted
        before re-insert using the latest computed fee components.
        """
        stmt = select(DBTransaction).filter_by(transaction_id=transaction_result.transaction_id)
        result = await self.db.execute(stmt)
        db_txn = result.scalars().first()
        if not db_txn:
            return

        await self.db.execute(
            TransactionCost.__table__.delete().where(
                TransactionCost.transaction_id == transaction_result.transaction_id
            )
        )

        self.db.add_all(
            _transaction_cost_rows(transaction_result=transaction_result, db_txn=db_txn)
        )

    async def upsert_buy_lot_state(self, transaction_result: EngineTransaction) -> None:
        """Persists BUY lot state as a durable, idempotent record."""
        stmt = pg_insert(PositionLotState).values(**buy_lot_state_payload(transaction_result))
        update_dict = mutable_lot_state_fields(stmt)
        await self.db.execute(
            stmt.on_conflict_do_update(index_elements=["source_transaction_id"], set_=update_dict)
        )

    async def update_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
    ) -> None:
        """Reconciles persisted quantity and cost with the latest engine-derived lot state."""
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = select(PositionLotState).where(
            func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
            func.trim(PositionLotState.security_id) == normalized_security_id,
        )
        lot_rows = (await self.db.execute(stmt)).scalars().all()
        for lot_row in lot_rows:
            state = states_by_source_transaction_id.get(lot_row.source_transaction_id)
            if state is None:
                lot_row.open_quantity = Decimal(0)
                lot_row.lot_cost_local = Decimal(0)
                lot_row.lot_cost_base = Decimal(0)
                continue
            lot_row.open_quantity = state.quantity
            lot_row.lot_cost_local = state.cost_local
            lot_row.lot_cost_base = state.cost_base

    async def update_selected_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
    ) -> None:
        """Update selected source lots without closing omitted positions."""

        if not states_by_source_transaction_id:
            return

        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        source_transaction_ids = set(states_by_source_transaction_id)
        stmt = select(PositionLotState).where(
            func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
            func.trim(PositionLotState.security_id) == normalized_security_id,
            PositionLotState.source_transaction_id.in_(source_transaction_ids),
        )
        lot_rows = (await self.db.execute(stmt)).scalars().all()
        persisted_source_ids = {lot_row.source_transaction_id for lot_row in lot_rows}
        missing_source_ids = source_transaction_ids - persisted_source_ids
        if missing_source_ids:
            missing_ids = ", ".join(sorted(missing_source_ids))
            raise ValueError(f"Selected cost-basis source lots are missing: {missing_ids}")

        for lot_row in lot_rows:
            state = states_by_source_transaction_id[lot_row.source_transaction_id]
            lot_row.open_quantity = state.quantity
            lot_row.lot_cost_local = state.cost_local
            lot_row.lot_cost_base = state.cost_base

    async def upsert_accrued_income_offset_state(
        self, transaction_result: EngineTransaction
    ) -> None:
        """Initializes or updates accrued-income offset state for BUY transactions."""
        accrued_interest_local = getattr(transaction_result, "accrued_interest", None) or Decimal(0)
        payload = {
            "offset_id": f"AIO-{transaction_result.transaction_id}",
            "source_transaction_id": transaction_result.transaction_id,
            "portfolio_id": transaction_result.portfolio_id,
            "instrument_id": transaction_result.instrument_id,
            "security_id": transaction_result.security_id,
            "accrued_interest_paid_local": accrued_interest_local,
            "remaining_offset_local": accrued_interest_local,
            "economic_event_id": getattr(transaction_result, "economic_event_id", None),
            "linked_transaction_group_id": getattr(
                transaction_result, "linked_transaction_group_id", None
            ),
            "calculation_policy_id": getattr(transaction_result, "calculation_policy_id", None),
            "calculation_policy_version": getattr(
                transaction_result, "calculation_policy_version", None
            ),
            "source_system": getattr(transaction_result, "source_system", None),
        }
        stmt = pg_insert(AccruedIncomeOffsetState).values(**payload)
        update_dict = {
            c.name: c
            for c in stmt.excluded
            if c.name not in ["id", "offset_id", "source_transaction_id"]
        }
        await self.db.execute(
            stmt.on_conflict_do_update(index_elements=["source_transaction_id"], set_=update_dict)
        )
