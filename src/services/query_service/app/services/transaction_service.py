# services/query-service/app/services/transaction_service.py
import logging
from datetime import date
from decimal import Decimal
from typing import Any, Optional, cast

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..dtos.transaction_dto import (
    PaginatedTransactionResponse,
    PortfolioRealizedTaxSummaryResponse,
    TransactionRecord,
)
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.transaction_repository import TransactionRepository
from .fx_conversion import CachedFxRateConverter
from .portfolio_validation import ensure_portfolio_exists
from .transaction_metadata import (
    latest_transaction_evidence_timestamp,
    ledger_data_quality_status,
)
from .transaction_realized_tax import realized_tax_currency_totals
from .transaction_reporting_currency import apply_transaction_reporting_currency_fields

logger = logging.getLogger(__name__)


class TransactionService:
    """
    Handles the business logic for querying transaction data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TransactionRepository(db)
        self._fx_converter = CachedFxRateConverter(self.repo)

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

        needs_default_as_of_date = as_of_date is None and not include_projected
        await ensure_portfolio_exists(repository=self.repo, portfolio_id=portfolio_id)
        default_as_of_date = (
            await self.repo.get_latest_business_date() if needs_default_as_of_date else as_of_date
        )

        effective_as_of_date = default_as_of_date
        if effective_as_of_date is None and needs_default_as_of_date:
            effective_as_of_date = date.today()

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

        db_results: list[Any]
        if total_count == 0:
            db_results = []
            latest_evidence_timestamp = None
        else:
            db_results = await self.repo.get_transactions(
                skip=skip,
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order,
                **ledger_filters,
            )
            if skip > 0 or limit < total_count:
                latest_evidence_timestamp = await self.repo.get_latest_evidence_timestamp(
                    **ledger_filters
                )
            else:
                if len(db_results) == total_count:
                    latest_evidence_timestamp = latest_transaction_evidence_timestamp(db_results)
                else:
                    latest_evidence_timestamp = await self.repo.get_latest_evidence_timestamp(
                        **ledger_filters
                    )
        resolved_reporting_currency = reporting_currency

        transactions = []
        for transaction in db_results:
            record = TransactionRecord.model_validate(transaction)
            record.costs = [cost for cost in transaction.costs or []]
            if transaction.cashflow:
                record.cashflow = transaction.cashflow
            if resolved_reporting_currency and effective_as_of_date is not None:
                await apply_transaction_reporting_currency_fields(
                    record=record,
                    reporting_currency=resolved_reporting_currency,
                    as_of_date=effective_as_of_date,
                    convert_amount=self._convert_amount,
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
                data_quality_status=ledger_data_quality_status(
                    total_count=total_count,
                    returned_count=len(transactions),
                    skip=skip,
                ),
                latest_evidence_timestamp=latest_evidence_timestamp,
            ),
        )

    async def get_realized_tax_summary(
        self,
        *,
        portfolio_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
        reporting_currency: Optional[str] = None,
    ) -> PortfolioRealizedTaxSummaryResponse:
        logger.info("Fetching realized tax summary for portfolio '%s'.", portfolio_id)

        base_currency = await self.repo.get_portfolio_base_currency(portfolio_id)
        if base_currency is None:
            raise LookupError(f"Portfolio with id {portfolio_id} not found")
        default_as_of_date = (
            await self.repo.get_latest_business_date() if as_of_date is None else as_of_date
        )
        normalized_base_currency = normalize_currency_code(str(base_currency))
        resolved_reporting_currency = (
            normalize_currency_code(reporting_currency) if reporting_currency is not None else None
        )

        effective_as_of_date = default_as_of_date or date.today()
        ledger_filters = {
            "portfolio_id": portfolio_id,
            "start_date": start_date,
            "end_date": end_date,
            "as_of_date": effective_as_of_date,
        }
        source_transaction_count = await self.repo.get_transactions_count(**ledger_filters)
        tax_transactions = await self.repo.list_realized_tax_evidence_transactions(
            **ledger_filters,
        )
        latest_evidence_timestamp = latest_transaction_evidence_timestamp(tax_transactions)

        currency_totals = realized_tax_currency_totals(tax_transactions)
        reporting_currency_total = None
        if resolved_reporting_currency is not None:
            converted_currency_totals = []
            for total in currency_totals:
                converted_currency_totals.append(
                    await self._convert_amount(
                        amount=total.total_tax_amount,
                        from_currency=total.currency,
                        to_currency=resolved_reporting_currency,
                        as_of_date=effective_as_of_date,
                    )
                )
            reporting_currency_total = sum(converted_currency_totals, Decimal("0"))

        return PortfolioRealizedTaxSummaryResponse(
            portfolio_id=portfolio_id,
            base_currency=normalized_base_currency,
            reporting_currency=resolved_reporting_currency,
            start_date=start_date,
            end_date=end_date,
            source_transaction_count=source_transaction_count,
            tax_evidence_transaction_count=sum(
                total.transaction_count for total in currency_totals
            ),
            currency_totals=currency_totals,
            reporting_currency_total_tax_amount=reporting_currency_total,
            reason_codes=[
                "PORTFOLIO_REALIZED_TAX_SUMMARY_READY"
                if currency_totals
                else "PORTFOLIO_REALIZED_TAX_EVIDENCE_EMPTY"
            ],
            **source_data_product_runtime_metadata(
                as_of_date=effective_as_of_date,
                data_quality_status=ledger_data_quality_status(
                    total_count=source_transaction_count,
                    returned_count=source_transaction_count,
                    skip=0,
                ),
                latest_evidence_timestamp=latest_evidence_timestamp,
            ),
        )

    async def _convert_amount(
        self,
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        return cast(
            Decimal,
            await self._fx_converter.convert_amount(
                amount=amount,
                from_currency=from_currency,
                to_currency=to_currency,
                as_of_date=as_of_date,
            ),
        )

    async def _get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        return cast(
            Decimal,
            await self._fx_converter.get_fx_rate(from_currency, to_currency, as_of_date),
        )
