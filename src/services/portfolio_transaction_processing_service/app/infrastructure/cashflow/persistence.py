"""Persist transaction-processing cashflows without leaking mutable ORM rows."""

import logging

from portfolio_common.database_models import Cashflow, Portfolio, Transaction
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cashflow import CalculatedCashflow, StoredCashflow

logger = logging.getLogger(__name__)


class SqlAlchemyCashflowRepository:
    """Persist calculated cashflows in the transaction-processing ledger."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        result = await self._session.execute(
            select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id)
        )
        return result.scalar_one_or_none() is not None

    async def transaction_exists(
        self, transaction_id: str, *, portfolio_id: str | None = None
    ) -> bool:
        stmt = select(Transaction.transaction_id).where(
            Transaction.transaction_id == transaction_id
        )
        if portfolio_id is not None:
            stmt = stmt.where(Transaction.portfolio_id == portfolio_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        cashflow: CalculatedCashflow | Cashflow,
    ) -> StoredCashflow:
        """Stage a cashflow or return the existing transaction/epoch row."""
        cashflow_row = _to_cashflow_row(cashflow)
        try:
            async with self._session.begin_nested():
                self._session.add(cashflow_row)
                await self._session.flush()
            await self._session.refresh(cashflow_row)
            logger.debug(
                "Successfully staged cashflow record for transaction_id '%s' in epoch %s",
                cashflow_row.transaction_id,
                cashflow_row.epoch,
            )
            return _to_stored_cashflow(cashflow_row)
        except IntegrityError:
            logger.debug(
                "Cashflow for transaction_id '%s' in epoch %s already exists. "
                "Reusing persisted row.",
                cashflow_row.transaction_id,
                cashflow_row.epoch,
            )
            result = await self._session.execute(
                select(Cashflow).where(
                    Cashflow.transaction_id == cashflow_row.transaction_id,
                    Cashflow.epoch == cashflow_row.epoch,
                )
            )
            existing_cashflow = result.scalars().first()
            if existing_cashflow is None:
                raise
            return _to_stored_cashflow(existing_cashflow)
        except Exception:
            logger.exception(
                "Unexpected error while staging cashflow for transaction_id '%s'",
                cashflow_row.transaction_id,
            )
            raise

    async def replace(
        self,
        cashflow: CalculatedCashflow | Cashflow,
    ) -> StoredCashflow:
        """Atomically restore the canonical transaction/epoch cashflow."""
        values = _cashflow_values(cashflow)
        insert_statement = pg_insert(Cashflow).values(**values)
        update_values = {
            field_name: getattr(insert_statement.excluded, field_name)
            for field_name in values
            if field_name not in {"transaction_id", "epoch"}
        }
        update_values["updated_at"] = func.now()
        cashflow_id = (
            await self._session.execute(
                insert_statement.on_conflict_do_update(
                    constraint="_transaction_epoch_uc",
                    set_=update_values,
                ).returning(Cashflow.id)
            )
        ).scalar_one()
        stored = (
            await self._session.execute(select(Cashflow).where(Cashflow.id == cashflow_id))
        ).scalar_one()
        return _to_stored_cashflow(stored)


def _cashflow_values(
    cashflow: CalculatedCashflow | Cashflow,
) -> dict[str, object]:
    return {
        "transaction_id": cashflow.transaction_id,
        "portfolio_id": cashflow.portfolio_id,
        "security_id": cashflow.security_id,
        "cashflow_date": cashflow.cashflow_date,
        "epoch": cashflow.epoch,
        "amount": cashflow.amount,
        "currency": cashflow.currency,
        "classification": cashflow.classification,
        "timing": cashflow.timing,
        "calculation_type": cashflow.calculation_type,
        "is_position_flow": cashflow.is_position_flow,
        "is_portfolio_flow": cashflow.is_portfolio_flow,
        "economic_event_id": cashflow.economic_event_id,
        "linked_transaction_group_id": cashflow.linked_transaction_group_id,
    }


def _to_cashflow_row(cashflow: CalculatedCashflow | Cashflow) -> Cashflow:
    if isinstance(cashflow, Cashflow):
        return cashflow
    return Cashflow(
        transaction_id=cashflow.transaction_id,
        portfolio_id=cashflow.portfolio_id,
        security_id=cashflow.security_id,
        cashflow_date=cashflow.cashflow_date,
        epoch=cashflow.epoch,
        amount=cashflow.amount,
        currency=cashflow.currency,
        classification=cashflow.classification,
        timing=cashflow.timing,
        calculation_type=cashflow.calculation_type,
        is_position_flow=cashflow.is_position_flow,
        is_portfolio_flow=cashflow.is_portfolio_flow,
        economic_event_id=cashflow.economic_event_id,
        linked_transaction_group_id=cashflow.linked_transaction_group_id,
    )


def _to_stored_cashflow(cashflow: Cashflow) -> StoredCashflow:
    if cashflow.id is None:
        raise RuntimeError("Persisted cashflow is missing its database identity")
    return StoredCashflow(
        cashflow_id=int(cashflow.id),
        transaction_id=str(cashflow.transaction_id),
        portfolio_id=str(cashflow.portfolio_id),
        security_id=(str(cashflow.security_id) if cashflow.security_id is not None else None),
        cashflow_date=cashflow.cashflow_date,
        epoch=int(cashflow.epoch),
        amount=cashflow.amount,
        currency=str(cashflow.currency),
        classification=str(cashflow.classification),
        timing=str(cashflow.timing),
        calculation_type=str(cashflow.calculation_type),
        is_position_flow=bool(cashflow.is_position_flow),
        is_portfolio_flow=bool(cashflow.is_portfolio_flow),
        economic_event_id=(
            str(cashflow.economic_event_id) if cashflow.economic_event_id is not None else None
        ),
        linked_transaction_group_id=(
            str(cashflow.linked_transaction_group_id)
            if cashflow.linked_transaction_group_id is not None
            else None
        ),
    )
