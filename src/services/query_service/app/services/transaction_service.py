# services/query-service/app/services/transaction_service.py
import logging
from datetime import date
from decimal import Decimal
from typing import NoReturn, Optional, cast

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.tenant import TenantContext
from portfolio_common.logging_utils import operation_log_extra
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.transaction_query import TransactionRecordUnavailableError
from ..dtos.transaction_dto import (
    PaginatedTransactionResponse,
    PortfolioRealizedTaxSummaryResponse,
    TransactionRecordResponse,
)
from ..repositories.transaction_repository import TransactionRepository
from .fx_conversion import CachedFxRateConverter
from .portfolio_validation import ensure_portfolio_owned
from .transaction_dates import (
    realized_tax_effective_as_of_date,
    transaction_ledger_effective_as_of_date,
)
from .transaction_metadata import (
    realized_tax_summary_filters,
    transaction_ledger_filters,
)
from .transaction_reads import (
    read_exact_transaction_ledger_record,
    read_realized_tax_evidence,
    read_transaction_ledger_page,
)
from .transaction_realized_tax import (
    portfolio_realized_tax_summary_response,
    realized_tax_currency_totals,
    realized_tax_reporting_currency_total,
)
from .transaction_records import (
    exact_transaction_record_response,
    paginated_transaction_ledger_response,
    transaction_records_from_rows,
)

logger = logging.getLogger(__name__)


def _raise_transaction_record_unavailable(
    exc: Exception,
    *,
    reason_code: str,
) -> NoReturn:
    logger.error(
        "Exact transaction source resolution failed.",
        extra=operation_log_extra(
            event_name="query.transaction_service.record_unavailable",
            operation="query.transaction_service.get_transaction_record",
            status="failed",
            reason_code=reason_code,
        ),
    )
    raise TransactionRecordUnavailableError(
        "Transaction record source is temporarily unavailable"
    ) from exc


class TransactionService:
    """
    Handles the business logic for querying transaction data.
    """

    def __init__(self, db: AsyncSession):
        self.repo = TransactionRepository(db)
        self._fx_converter = CachedFxRateConverter(self.repo)

    async def get_transactions(
        self,
        *,
        tenant_context: TenantContext,
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
        logger.info(
            "Transaction ledger query requested.",
            extra=operation_log_extra(
                event_name="query.transaction_service.ledger_requested",
                operation="query.transaction_service.get_transactions",
                status="started",
                reason_code="request_received",
                has_instrument_filter=instrument_id is not None,
                has_security_filter=security_id is not None,
                has_transaction_type_filter=transaction_type is not None,
                has_component_type_filter=component_type is not None,
                has_start_date_filter=start_date is not None,
                has_end_date_filter=end_date is not None,
                has_as_of_date_filter=as_of_date is not None,
                include_projected=include_projected,
                has_reporting_currency=reporting_currency is not None,
            ),
        )

        await self.repo.establish_transaction_ledger_read_snapshot()
        await ensure_portfolio_owned(
            repository=self.repo,
            tenant_id=tenant_context.tenant_id_text,
            portfolio_id=portfolio_id,
        )
        effective_as_of_date = await transaction_ledger_effective_as_of_date(
            repository=self.repo,
            as_of_date=as_of_date,
            include_projected=include_projected,
        )

        ledger_filters = transaction_ledger_filters(
            portfolio_id=portfolio_id,
            transaction_id=None,
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
            reporting_currency=reporting_currency,
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
            ledger_filters=ledger_filters,
            input_evidence=ledger_page.input_evidence,
            missing_instrument_security_ids=ledger_page.missing_instrument_security_ids,
        )

    async def get_transaction_record(
        self,
        *,
        tenant_context: TenantContext,
        portfolio_id: str,
        transaction_id: str,
        as_of_date: date | None = None,
        include_projected: bool = False,
        reporting_currency: str | None = None,
    ) -> TransactionRecordResponse:
        """Return one portfolio-owned transaction with complete ledger proof metadata."""

        resolved_reporting_currency = (
            normalize_currency_code(reporting_currency) if reporting_currency is not None else None
        )
        logger.info(
            "Exact transaction record query requested.",
            extra=operation_log_extra(
                event_name="query.transaction_service.record_requested",
                operation="query.transaction_service.get_transaction_record",
                status="started",
                reason_code="request_received",
                has_as_of_date_filter=as_of_date is not None,
                include_projected=include_projected,
                has_reporting_currency=reporting_currency is not None,
            ),
        )
        try:
            await self.repo.establish_transaction_ledger_read_snapshot()
            await ensure_portfolio_owned(
                repository=self.repo,
                tenant_id=tenant_context.tenant_id_text,
                portfolio_id=portfolio_id,
            )
            effective_as_of_date = await transaction_ledger_effective_as_of_date(
                repository=self.repo,
                as_of_date=as_of_date,
                include_projected=include_projected,
            )
            ledger_filters = transaction_ledger_filters(
                portfolio_id=portfolio_id,
                transaction_id=transaction_id,
                instrument_id=None,
                security_id=None,
                transaction_type=None,
                component_type=None,
                linked_transaction_group_id=None,
                fx_contract_id=None,
                swap_event_id=None,
                near_leg_group_id=None,
                far_leg_group_id=None,
                start_date=None,
                end_date=None,
                as_of_date=effective_as_of_date,
            )
            ledger_page = await read_exact_transaction_ledger_record(
                repository=self.repo,
                ledger_filters=ledger_filters,
                reporting_currency=resolved_reporting_currency,
            )
        except SQLAlchemyError as exc:
            _raise_transaction_record_unavailable(exc, reason_code="source_query_failed")

        if ledger_page.total_count == 0:
            raise LookupError("Transaction record not found for requested portfolio")
        if ledger_page.total_count != 1 or len(ledger_page.rows) != 1:
            raise TransactionRecordUnavailableError(
                "Transaction record source returned inconsistent identity evidence"
            )
        record_as_of_date = ledger_page.evidence_as_of_date
        if record_as_of_date is None:
            raise TransactionRecordUnavailableError(
                "Transaction record source returned incomplete temporal evidence"
            )

        try:
            records = await transaction_records_from_rows(
                rows=ledger_page.rows,
                reporting_currency=resolved_reporting_currency,
                as_of_date=record_as_of_date,
                convert_amount=self._convert_amount,
            )
        except SQLAlchemyError as exc:
            _raise_transaction_record_unavailable(exc, reason_code="source_query_failed")
        except ValueError as exc:
            _raise_transaction_record_unavailable(exc, reason_code="source_evidence_invalid")
        if len(records) != 1:
            raise TransactionRecordUnavailableError(
                "Transaction record source returned inconsistent mapped evidence"
            )
        try:
            return exact_transaction_record_response(
                portfolio_id=portfolio_id,
                reporting_currency=resolved_reporting_currency,
                transaction=records[0],
                effective_as_of_date=record_as_of_date,
                latest_evidence_timestamp=ledger_page.latest_evidence_timestamp,
                ledger_filters=ledger_filters,
                input_evidence=ledger_page.input_evidence,
                missing_instrument_security_ids=ledger_page.missing_instrument_security_ids,
            )
        except ValueError as exc:
            _raise_transaction_record_unavailable(exc, reason_code="source_evidence_invalid")

    async def get_realized_tax_summary(
        self,
        *,
        tenant_context: TenantContext,
        portfolio_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
        reporting_currency: Optional[str] = None,
    ) -> PortfolioRealizedTaxSummaryResponse:
        logger.info(
            "Realized tax summary query requested.",
            extra=operation_log_extra(
                event_name="query.transaction_service.realized_tax_requested",
                operation="query.transaction_service.get_realized_tax_summary",
                status="started",
                reason_code="request_received",
                has_start_date_filter=start_date is not None,
                has_end_date_filter=end_date is not None,
                has_as_of_date_filter=as_of_date is not None,
                has_reporting_currency=reporting_currency is not None,
            ),
        )

        await ensure_portfolio_owned(
            repository=self.repo,
            tenant_id=tenant_context.tenant_id_text,
            portfolio_id=portfolio_id,
        )
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
