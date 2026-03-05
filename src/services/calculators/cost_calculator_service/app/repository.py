# services/calculators/cost_calculator_service/app/repository.py
from datetime import date
from decimal import Decimal
from typing import List, Optional

from core.models.transaction import Transaction as EngineTransaction
from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    FxRate,
    Portfolio,
    PositionLotState,
    TransactionCost,
)
from portfolio_common.database_models import (
    Transaction as DBTransaction,
)
from portfolio_common.events import TransactionEvent
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


class CostCalculatorRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Fetches a portfolio by its portfolio_id string."""
        stmt = select(Portfolio).where(Portfolio.portfolio_id == portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_fx_rate(
        self, from_currency: str, to_currency: str, a_date: date
    ) -> Optional[FxRate]:
        """Fetches the latest FX rate on or before a given date."""
        stmt = (
            select(FxRate)
            .filter(
                FxRate.from_currency == from_currency,
                FxRate.to_currency == to_currency,
                FxRate.rate_date <= a_date,
            )
            .order_by(FxRate.rate_date.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_transaction_history(
        self, portfolio_id: str, security_id: str, exclude_id: Optional[str] = None
    ) -> List[DBTransaction]:
        """
        Fetches all transactions for a given security in a portfolio,
        optionally excluding one by its transaction_id.
        """
        stmt = select(DBTransaction).filter_by(portfolio_id=portfolio_id, security_id=security_id)

        if exclude_id:
            stmt = stmt.filter(DBTransaction.transaction_id != exclude_id)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_transaction_costs(
        self, transaction_result: EngineTransaction
    ) -> DBTransaction | None:
        """Finds a transaction by its ID and updates its calculated cost fields."""
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

        return db_txn_to_update

    async def get_transaction_by_id(
        self, transaction_id: str, *, portfolio_id: str | None = None
    ) -> DBTransaction | None:
        stmt = select(DBTransaction).where(DBTransaction.transaction_id == transaction_id)
        if portfolio_id:
            stmt = stmt.where(DBTransaction.portfolio_id == portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def create_or_update_transaction_event(self, event: TransactionEvent) -> DBTransaction:
        event_dict = event.model_dump(
            exclude={"epoch", "brokerage", "stamp_duty", "exchange_fee", "gst", "other_fees"},
            exclude_none=True,
        )
        stmt = pg_insert(DBTransaction).values(**event_dict)
        update_fields = [k for k in event_dict.keys() if k not in {"id", "transaction_id"}]
        update_dict = {field: getattr(stmt.excluded, field) for field in update_fields}
        await self.db.execute(
            stmt.on_conflict_do_update(index_elements=["transaction_id"], set_=update_dict)
        )
        return DBTransaction(**event_dict)

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

        fees = transaction_result.fees
        if not fees:
            return

        fee_components = {
            "brokerage": fees.brokerage,
            "stamp_duty": fees.stamp_duty,
            "exchange_fee": fees.exchange_fee,
            "gst": fees.gst,
            "other_fees": fees.other_fees,
        }
        for fee_type, amount in fee_components.items():
            if (amount or Decimal(0)) <= 0:
                continue
            self.db.add(
                TransactionCost(
                    transaction_id=transaction_result.transaction_id,
                    fee_type=fee_type,
                    amount=amount,
                    currency=db_txn.trade_currency or db_txn.currency,
                )
            )

    async def upsert_buy_lot_state(self, transaction_result: EngineTransaction) -> None:
        """Persists BUY lot state as a durable, idempotent record."""
        accrued_interest_local = getattr(transaction_result, "accrued_interest", None) or Decimal(0)
        lot_payload = {
            "lot_id": f"LOT-{transaction_result.transaction_id}",
            "source_transaction_id": transaction_result.transaction_id,
            "portfolio_id": transaction_result.portfolio_id,
            "instrument_id": transaction_result.instrument_id,
            "security_id": transaction_result.security_id,
            "acquisition_date": transaction_result.transaction_date.date(),
            "original_quantity": transaction_result.quantity,
            "open_quantity": transaction_result.quantity,
            "lot_cost_local": transaction_result.net_cost_local or Decimal(0),
            "lot_cost_base": transaction_result.net_cost or Decimal(0),
            "accrued_interest_paid_local": accrued_interest_local,
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
        stmt = pg_insert(PositionLotState).values(**lot_payload)
        update_dict = {
            c.name: c
            for c in stmt.excluded
            if c.name not in ["id", "lot_id", "source_transaction_id"]
        }
        await self.db.execute(
            stmt.on_conflict_do_update(index_elements=["source_transaction_id"], set_=update_dict)
        )

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
