# services/persistence_service/app/repositories/transaction_db_repo.py
import logging
from dataclasses import dataclass
from datetime import date

from portfolio_common.database_models import CashAccountMaster, Instrument, Portfolio
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy import exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.event_record_mapper import transaction_event_to_record_values

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TransactionReferenceAvailability:
    """Reference state required to accept one transaction into the raw ledger."""

    portfolio_exists: bool
    instrument_exists: bool
    cash_account_exists: bool | None


class TransactionDBRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_transaction_reference_availability(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        cash_account_id: str | None,
        cash_security_id: str | None,
        as_of_date: date,
    ) -> TransactionReferenceAvailability:
        """Resolve portfolio, instrument, and optional cash-account state in one database read."""
        normalized_security_id = security_id.strip()
        normalized_cash_account_id = (cash_account_id or "").strip()
        normalized_cash_security_id = (cash_security_id or "").strip()

        instrument_exists = (
            exists().where(func.trim(Instrument.security_id) == normalized_security_id)
            if normalized_security_id
            else literal(False)
        )
        cash_account_exists = literal(None)
        if normalized_cash_account_id:
            cash_account_conditions = [
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
            if normalized_cash_security_id:
                cash_account_conditions.append(
                    func.trim(CashAccountMaster.security_id) == normalized_cash_security_id
                )
            cash_account_exists = exists().where(*cash_account_conditions)

        statement = select(
            exists().where(Portfolio.portfolio_id == portfolio_id),
            instrument_exists,
            cash_account_exists,
        )
        result = await self.db.execute(statement)
        portfolio_available, instrument_available, cash_account_available = result.one()
        return TransactionReferenceAvailability(
            portfolio_exists=bool(portfolio_available),
            instrument_exists=bool(instrument_available),
            cash_account_exists=(
                bool(cash_account_available) if cash_account_available is not None else None
            ),
        )

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
            logger.debug(
                "Transaction upsert staged.",
                extra={"transaction_id": event.transaction_id},
            )

            # Note: Since UPSERT doesn't easily return the model, we can assume success.
            # The calling consumer logic doesn't depend on the returned object.
            return DBTransaction(**event_dict)

        except Exception:
            logger.error(
                "Failed to stage transaction upsert.",
                extra={"transaction_id": event.transaction_id},
                exc_info=True,
            )
            raise
