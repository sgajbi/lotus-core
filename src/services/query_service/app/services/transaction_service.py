# services/query-service/app/services/transaction_service.py
import logging
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..dtos.transaction_dto import PaginatedTransactionResponse, TransactionRecord
from ..repositories.transaction_repository import TransactionRepository

logger = logging.getLogger(__name__)


class TransactionService:
    """
    Handles the business logic for querying transaction data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TransactionRepository(db)

    async def get_transactions(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = "desc",
        instrument_id: Optional[str] = None,
        security_id: Optional[str] = None,
        transaction_type: Optional[str] = None,
        component_type: Optional[str] = None,
        linked_transaction_group_id: Optional[str] = None,
        fx_contract_id: Optional[str] = None,
        swap_event_id: Optional[str] = None,
        near_leg_group_id: Optional[str] = None,
        far_leg_group_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
        include_projected: bool = False,
    ) -> PaginatedTransactionResponse:
        """
        Retrieves a paginated and filtered list of transactions for a portfolio.
        """
        logger.info(f"Fetching transactions for portfolio '{portfolio_id}'.")

        if not await self.repo.portfolio_exists(portfolio_id):
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

        effective_as_of_date = as_of_date
        if effective_as_of_date is None and not include_projected:
            effective_as_of_date = await self.repo.get_latest_business_date() or date.today()

        total_count = await self.repo.get_transactions_count(
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            security_id=security_id,
            transaction_type=transaction_type,
            component_type=component_type,
            linked_transaction_group_id=linked_transaction_group_id,
            fx_contract_id=fx_contract_id,
            swap_event_id=swap_event_id,
            near_leg_group_id=near_leg_group_id,
            far_leg_group_id=far_leg_group_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=effective_as_of_date,
        )

        db_results = await self.repo.get_transactions(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            instrument_id=instrument_id,
            security_id=security_id,
            transaction_type=transaction_type,
            component_type=component_type,
            linked_transaction_group_id=linked_transaction_group_id,
            fx_contract_id=fx_contract_id,
            swap_event_id=swap_event_id,
            near_leg_group_id=near_leg_group_id,
            far_leg_group_id=far_leg_group_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=effective_as_of_date,
        )

        transactions = []
        for transaction in db_results:
            record = TransactionRecord.model_validate(transaction)
            record.costs = [cost for cost in transaction.costs or []]
            if transaction.cashflow:
                record.cashflow = transaction.cashflow
            transactions.append(record)

        return PaginatedTransactionResponse(
            portfolio_id=portfolio_id,
            total=total_count,
            skip=skip,
            limit=limit,
            transactions=transactions,
            **source_data_product_runtime_metadata(
                as_of_date=effective_as_of_date or end_date or date.today(),
            ),
        )
