"""Persist transaction-processing cashflows without leaking mutable ORM rows."""

import logging

from portfolio_common.database_models import Cashflow, Portfolio, Transaction
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
        values = _cashflow_values(cashflow)
        try:
            inserted_id = (
                await self._session.execute(
                    pg_insert(Cashflow)
                    .values(**values)
                    .on_conflict_do_nothing(constraint="_transaction_epoch_uc")
                    .returning(Cashflow.id)
                )
            ).scalar_one_or_none()
            if inserted_id is not None:
                logger.debug(
                    "Successfully staged cashflow record for transaction_id '%s' in epoch %s",
                    cashflow.transaction_id,
                    cashflow.epoch,
                )
                return _to_stored_cashflow(cashflow, cashflow_id=int(inserted_id))

            logger.debug(
                "Cashflow for transaction_id '%s' in epoch %s already exists. "
                "Reusing persisted row.",
                cashflow.transaction_id,
                cashflow.epoch,
            )
            result = await self._session.execute(
                select(Cashflow).where(
                    Cashflow.transaction_id == cashflow.transaction_id,
                    Cashflow.epoch == cashflow.epoch,
                )
            )
            existing_cashflow = result.scalars().first()
            if existing_cashflow is None:
                raise RuntimeError(
                    "Cashflow insert conflicted without an existing transaction/epoch row"
                )
            return _to_stored_cashflow(existing_cashflow)
        except Exception:
            logger.exception(
                "Unexpected error while staging cashflow for transaction_id '%s'",
                cashflow.transaction_id,
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
        return _to_stored_cashflow(cashflow, cashflow_id=int(cashflow_id))


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


def _to_stored_cashflow(
    cashflow: CalculatedCashflow | Cashflow,
    *,
    cashflow_id: int | None = None,
) -> StoredCashflow:
    resolved_cashflow_id = cashflow_id or getattr(cashflow, "id", None)
    if resolved_cashflow_id is None:
        raise RuntimeError("Persisted cashflow is missing its database identity")
    return StoredCashflow(
        cashflow_id=int(resolved_cashflow_id),
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
