# services/persistence_service/app/repositories/transaction_db_repo.py
import logging
from datetime import date

from portfolio_common.database_models import CashAccountMaster, Instrument, Portfolio
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent, event_business_payload
from sqlalchemy import exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_TRANSACTION_EVENT_ONLY_FIELDS = frozenset(
    {
        "epoch",
        "brokerage",
        "stamp_duty",
        "exchange_fee",
        "gst",
        "other_fees",
    }
)


def transaction_event_to_record_values(event: TransactionEvent) -> dict[str, object]:
    """Map a validated transaction event to transaction-table values."""
    payload = event_business_payload(event, mode="python")
    return {
        key: value
        for key, value in payload.items()
        if key not in _TRANSACTION_EVENT_ONLY_FIELDS and value is not None
    }


class TransactionDBRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_portfolio_exists(self, portfolio_id: str) -> bool:
        """Checks if a portfolio with the given ID exists in the database."""
        stmt = select(exists().where(Portfolio.portfolio_id == portfolio_id))
        result = await self.db.execute(stmt)
        return result.scalar()

    async def check_instrument_exists(self, security_id: str) -> bool:
        """Checks whether a governed instrument master row exists for a security."""
        normalized_security_id = security_id.strip()
        if not normalized_security_id:
            return False
        stmt = select(exists().where(func.trim(Instrument.security_id) == normalized_security_id))
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def check_active_cash_account_exists(
        self,
        *,
        portfolio_id: str,
        cash_account_id: str,
        cash_security_id: str | None,
        as_of_date: date,
    ) -> bool:
        """Checks whether an active/effective cash account master backs a transaction reference."""
        normalized_cash_account_id = cash_account_id.strip()
        if not normalized_cash_account_id:
            return False

        conditions = [
            CashAccountMaster.portfolio_id == portfolio_id,
            CashAccountMaster.cash_account_id == normalized_cash_account_id,
            func.upper(func.trim(CashAccountMaster.lifecycle_status)) == "ACTIVE",
            or_(
                CashAccountMaster.opened_on.is_(None),
                CashAccountMaster.opened_on <= as_of_date,
            ),
            or_(
                CashAccountMaster.closed_on.is_(None),
                CashAccountMaster.closed_on >= as_of_date,
            ),
        ]
        normalized_cash_security_id = (cash_security_id or "").strip()
        if normalized_cash_security_id:
            conditions.append(
                func.trim(CashAccountMaster.security_id) == normalized_cash_security_id
            )

        stmt = select(exists().where(*conditions))
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def create_or_update_transaction(self, event: TransactionEvent) -> DBTransaction:
        """
        Idempotently creates or updates a transaction using a native PostgreSQL
        UPSERT (INSERT ... ON CONFLICT DO UPDATE) for high performance and concurrency safety.
        """
        try:
            event_dict = transaction_event_to_record_values(event)

            # The statement to execute.
            stmt = pg_insert(DBTransaction).values(**event_dict)

            # Update only fields supplied by the event payload to avoid touching
            # unrelated columns during partial contract rollout.
            update_fields = [k for k in event_dict.keys() if k not in {"id", "transaction_id"}]
            update_dict = {field: getattr(stmt.excluded, field) for field in update_fields}

            # The final UPSERT statement with the conflict resolution.
            final_stmt = stmt.on_conflict_do_update(
                index_elements=["transaction_id"], set_=update_dict
            )

            await self.db.execute(final_stmt)
            logger.info(f"Successfully staged UPSERT for transaction '{event.transaction_id}'.")

            # Note: Since UPSERT doesn't easily return the model, we can assume success.
            # The calling consumer logic doesn't depend on the returned object.
            return DBTransaction(**event_dict)

        except Exception as e:
            logger.error(
                f"Failed to stage UPSERT for transaction '{event.transaction_id}': {e}",
                exc_info=True,
            )
            raise
