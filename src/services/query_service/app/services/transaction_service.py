# services/query-service/app/services/transaction_service.py
import logging
from datetime import date
from decimal import Decimal
from typing import Optional, cast

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.transaction_dto import PaginatedTransactionResponse, PortfolioRealizedTaxSummaryResponse
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.transaction_repository import TransactionRepository
from .fx_conversion import CachedFxRateConverter
from .portfolio_validation import ensure_portfolio_exists
from .transaction_dates import (
    realized_tax_effective_as_of_date,
    transaction_ledger_effective_as_of_date,
)
from .transaction_metadata import (
    realized_tax_summary_filters,
    transaction_ledger_filters,
)
from .transaction_reads import read_realized_tax_evidence, read_transaction_ledger_page
from .transaction_realized_tax import (
    portfolio_realized_tax_summary_response,
    realized_tax_currency_totals,
    realized_tax_reporting_currency_total,
)
from .transaction_records import (
    paginated_transaction_ledger_response,
    transaction_records_from_rows,
)

logger = logging.getLogger(__name__)


class TransactionService:
    """
    Handles the business logic for querying transaction data.
    """

    def __init__(self, db: AsyncSession):
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

        await ensure_portfolio_exists(repository=self.repo, portfolio_id=portfolio_id)
        effective_as_of_date = await transaction_ledger_effective_as_of_date(
            repository=self.repo,
            as_of_date=as_of_date,
            include_projected=include_projected,
        )

        ledger_filters = transaction_ledger_filters(
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

        ledger_page = await read_transaction_ledger_page(
            repository=self.repo,
            ledger_filters=ledger_filters,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        resolved_reporting_currency = reporting_currency

        transactions = await transaction_records_from_rows(
            rows=ledger_page.rows,
            reporting_currency=resolved_reporting_currency,
            as_of_date=effective_as_of_date,
            convert_amount=self._convert_amount,
        )

        return paginated_transaction_ledger_response(
            portfolio_id=portfolio_id,
            reporting_currency=resolved_reporting_currency,
            total_count=ledger_page.total_count,
            skip=skip,
            limit=limit,
            transactions=transactions,
            effective_as_of_date=effective_as_of_date,
            end_date=end_date,
            latest_evidence_timestamp=ledger_page.latest_evidence_timestamp,
            missing_instrument_security_ids=ledger_page.missing_instrument_security_ids,
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
        effective_as_of_date = await realized_tax_effective_as_of_date(
            repository=self.repo,
            as_of_date=as_of_date,
        )
        normalized_base_currency = normalize_currency_code(str(base_currency))
        resolved_reporting_currency = (
            normalize_currency_code(reporting_currency) if reporting_currency is not None else None
        )

        ledger_filters = realized_tax_summary_filters(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=effective_as_of_date,
        )
        realized_tax_evidence = await read_realized_tax_evidence(
            repository=self.repo,
            ledger_filters=ledger_filters,
        )

        currency_totals = realized_tax_currency_totals(realized_tax_evidence.tax_transactions)
        reporting_currency_total = await realized_tax_reporting_currency_total(
            currency_totals=currency_totals,
            reporting_currency=resolved_reporting_currency,
            as_of_date=effective_as_of_date,
            convert_amount=self._convert_amount,
        )

        return portfolio_realized_tax_summary_response(
            portfolio_id=portfolio_id,
            base_currency=normalized_base_currency,
            reporting_currency=resolved_reporting_currency,
            start_date=start_date,
            end_date=end_date,
            as_of_date=effective_as_of_date,
            source_transaction_count=realized_tax_evidence.source_transaction_count,
            currency_totals=currency_totals,
            reporting_currency_total_tax_amount=reporting_currency_total,
            latest_evidence_timestamp=realized_tax_evidence.latest_evidence_timestamp,
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
