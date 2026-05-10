# services/query-service/app/services/transaction_service.py
import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN
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
        self._fx_cache: dict[tuple[str, str, date], Decimal] = {}

    @staticmethod
    def _ledger_data_quality_status(
        *,
        total_count: int,
        returned_count: int,
        skip: int,
    ) -> str:
        if total_count <= 0:
            return UNKNOWN
        if skip > 0 or returned_count < total_count:
            return PARTIAL
        return COMPLETE

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
        reporting_currency: Optional[str] = None,
    ) -> PaginatedTransactionResponse:
        """
        Retrieves a paginated and filtered list of transactions for a portfolio.
        """
        logger.info(f"Fetching transactions for portfolio '{portfolio_id}'.")

        if not await self.repo.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")

        effective_as_of_date = as_of_date
        if effective_as_of_date is None and not include_projected:
            effective_as_of_date = await self.repo.get_latest_business_date() or date.today()

        ledger_filters = {
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_id,
            "security_id": security_id,
            "transaction_type": transaction_type,
            "component_type": component_type,
            "linked_transaction_group_id": linked_transaction_group_id,
            "fx_contract_id": fx_contract_id,
            "swap_event_id": swap_event_id,
            "near_leg_group_id": near_leg_group_id,
            "far_leg_group_id": far_leg_group_id,
            "start_date": start_date,
            "end_date": end_date,
            "as_of_date": effective_as_of_date,
        }

        total_count = await self.repo.get_transactions_count(**ledger_filters)

        db_results = await self.repo.get_transactions(
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            **ledger_filters,
        )
        latest_evidence_timestamp = await self.repo.get_latest_evidence_timestamp(**ledger_filters)
        resolved_reporting_currency = reporting_currency

        transactions = []
        for transaction in db_results:
            record = TransactionRecord.model_validate(transaction)
            record.costs = [cost for cost in transaction.costs or []]
            if transaction.cashflow:
                record.cashflow = transaction.cashflow
            if resolved_reporting_currency and effective_as_of_date is not None:
                await self._apply_reporting_currency_fields(
                    record=record,
                    reporting_currency=resolved_reporting_currency,
                    as_of_date=effective_as_of_date,
                )
            transactions.append(record)

        return PaginatedTransactionResponse(
            portfolio_id=portfolio_id,
            reporting_currency=resolved_reporting_currency,
            total=total_count,
            skip=skip,
            limit=limit,
            transactions=transactions,
            **source_data_product_runtime_metadata(
                as_of_date=effective_as_of_date or end_date or date.today(),
                data_quality_status=self._ledger_data_quality_status(
                    total_count=total_count,
                    returned_count=len(transactions),
                    skip=skip,
                ),
                latest_evidence_timestamp=latest_evidence_timestamp,
            ),
        )

    async def _apply_reporting_currency_fields(
        self,
        *,
        record: TransactionRecord,
        reporting_currency: str,
        as_of_date: date,
    ) -> None:
        money_fields = (
            ("gross_transaction_amount", "gross_transaction_amount_reporting_currency", "book"),
            ("gross_cost", "gross_cost_reporting_currency", "book"),
            ("trade_fee", "trade_fee_reporting_currency", "trade"),
            ("net_cost", "net_cost_reporting_currency", "book"),
            ("realized_gain_loss", "realized_gain_loss_reporting_currency", "book"),
            (
                "realized_capital_pnl_local",
                "realized_capital_pnl_local_reporting_currency",
                "trade",
            ),
            ("realized_fx_pnl_local", "realized_fx_pnl_local_reporting_currency", "trade"),
            ("realized_total_pnl_local", "realized_total_pnl_local_reporting_currency", "trade"),
            ("withholding_tax_amount", "withholding_tax_amount_reporting_currency", "book"),
            (
                "other_interest_deductions_amount",
                "other_interest_deductions_amount_reporting_currency",
                "book",
            ),
            ("net_interest_amount", "net_interest_amount_reporting_currency", "book"),
        )
        for source_field, target_field, currency_basis in money_fields:
            amount = getattr(record, source_field)
            if amount is None:
                continue
            setattr(
                record,
                target_field,
                await self._convert_amount(
                    amount=amount,
                    from_currency=self._source_currency_for_field(
                        record=record,
                        currency_basis=currency_basis,
                    ),
                    to_currency=reporting_currency,
                    as_of_date=as_of_date,
                ),
            )

    @staticmethod
    def _source_currency_for_field(
        *,
        record: TransactionRecord,
        currency_basis: str,
    ) -> str:
        if currency_basis == "trade" and record.trade_currency:
            return record.trade_currency
        return record.currency

    async def _convert_amount(
        self,
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        if from_currency == to_currency:
            return amount
        rate = await self._get_fx_rate(from_currency, to_currency, as_of_date)
        return amount * rate

    async def _get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        cache_key = (from_currency, to_currency, as_of_date)
        if cache_key in self._fx_cache:
            return self._fx_cache[cache_key]
        rate = await self.repo.get_latest_fx_rate(
            from_currency=from_currency,
            to_currency=to_currency,
            as_of_date=as_of_date,
        )
        if rate is None:
            raise ValueError(
                f"FX rate not found for {from_currency}/{to_currency} as of {as_of_date}."
            )
        resolved_rate = Decimal(str(rate))
        self._fx_cache[cache_key] = resolved_rate
        return resolved_rate
