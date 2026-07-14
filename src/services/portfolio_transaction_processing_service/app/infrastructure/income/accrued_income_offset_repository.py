"""SQLAlchemy persistence for accrued-income purchase offsets."""

from decimal import Decimal

from portfolio_common.database_models import AccruedIncomeOffsetState
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cost_basis import CostBasisTransaction


class SqlAlchemyAccruedIncomeOffsetRepository:
    """Persist remaining accrued income paid when a position is acquired."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_accrued_income_offset(
        self,
        transaction: CostBasisTransaction,
    ) -> None:
        """Idempotently initialize or refresh the purchase income offset."""

        accrued_interest_local = transaction.accrued_interest or Decimal(0)
        payload = {
            "offset_id": f"AIO-{transaction.transaction_id}",
            "source_transaction_id": transaction.transaction_id,
            "portfolio_id": transaction.portfolio_id,
            "instrument_id": transaction.instrument_id,
            "security_id": transaction.security_id,
            "accrued_interest_paid_local": accrued_interest_local,
            "remaining_offset_local": accrued_interest_local,
            "economic_event_id": getattr(transaction, "economic_event_id", None),
            "linked_transaction_group_id": getattr(
                transaction,
                "linked_transaction_group_id",
                None,
            ),
            "calculation_policy_id": getattr(transaction, "calculation_policy_id", None),
            "calculation_policy_version": getattr(
                transaction,
                "calculation_policy_version",
                None,
            ),
            "source_system": getattr(transaction, "source_system", None),
        }
        statement = pg_insert(AccruedIncomeOffsetState).values(**payload)
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["source_transaction_id"],
                set_={
                    column.name: column
                    for column in statement.excluded
                    if column.name not in {"id", "offset_id", "source_transaction_id"}
                },
            )
        )
