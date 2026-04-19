from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reporting_dto import CashAccountBalanceRecord, CashBalancesResponse, CashBalancesTotals
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.reporting_repository import ReportingRepository
from portfolio_common.reconciliation_quality import COMPLETE, UNKNOWN

ZERO = Decimal("0")
CASH_ASSET_CLASS = "CASH"


class CashBalanceResolver:
    def __init__(
        self,
        *,
        repo: ReportingRepository,
        convert_amount: Callable[..., Awaitable[Decimal]],
    ) -> None:
        self.repo = repo
        self._convert_amount = convert_amount

    async def build_cash_balances_response(
        self,
        *,
        portfolio: Any,
        resolved_as_of_date: date,
        reporting_currency: str,
        rows: list[Any],
    ) -> CashBalancesResponse:
        cash_rows = [row for row in rows if self.is_cash_row(row)]
        account_records = await self.build_cash_account_balance_records(
            portfolio=portfolio,
            cash_rows=cash_rows,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
        )
        return CashBalancesResponse(
            portfolio_id=portfolio.portfolio_id,
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            resolved_as_of_date=resolved_as_of_date,
            totals=CashBalancesTotals(
                cash_account_count=len(account_records),
                total_balance_portfolio_currency=sum(
                    (record.balance_portfolio_currency for record in account_records),
                    ZERO,
                ),
                total_balance_reporting_currency=sum(
                    (record.balance_reporting_currency for record in account_records),
                    ZERO,
                ),
            ),
            cash_accounts=account_records,
            **source_data_product_runtime_metadata(
                as_of_date=resolved_as_of_date,
                data_quality_status=self.data_quality_status(
                    cash_rows=cash_rows,
                    account_records=account_records,
                ),
                latest_evidence_timestamp=self.latest_snapshot_evidence_timestamp(cash_rows),
            ),
        )

    async def build_cash_account_balance_records(
        self,
        *,
        portfolio: Any,
        cash_rows: list[Any],
        resolved_as_of_date: date,
        reporting_currency: str,
    ) -> list[CashAccountBalanceRecord]:
        cash_security_ids = [row.snapshot.security_id for row in cash_rows]
        master_rows = await self.repo.list_cash_account_masters(
            portfolio_id=portfolio.portfolio_id,
            as_of_date=resolved_as_of_date,
        )
        master_by_security_id = {row.security_id: row for row in master_rows}
        fallback_cash_account_ids = await self.repo.get_latest_cash_account_ids(
            portfolio_id=portfolio.portfolio_id,
            cash_security_ids=cash_security_ids,
            as_of_date=resolved_as_of_date,
        )
        snapshot_by_security_id = {row.snapshot.security_id: row for row in cash_rows}

        account_records: list[CashAccountBalanceRecord] = []
        emitted_cash_account_ids: set[str] = set()

        for master_row in master_rows:
            snapshot_row = snapshot_by_security_id.get(master_row.security_id)
            account_record = await self._build_cash_account_balance_record(
                portfolio=portfolio,
                snapshot_row=snapshot_row,
                resolved_as_of_date=resolved_as_of_date,
                reporting_currency=reporting_currency,
                cash_account_id=master_row.cash_account_id,
                security_id=master_row.security_id,
                instrument_name=(
                    snapshot_row.instrument.name
                    if snapshot_row and snapshot_row.instrument
                    else master_row.display_name
                ),
                account_currency=master_row.account_currency,
            )
            account_records.append(account_record)
            emitted_cash_account_ids.add(master_row.cash_account_id)

        for cash_row in cash_rows:
            master_row = master_by_security_id.get(cash_row.snapshot.security_id)
            fallback_cash_account_id = (
                master_row.cash_account_id
                if master_row is not None
                else fallback_cash_account_ids.get(cash_row.snapshot.security_id)
                or cash_row.snapshot.security_id
            )
            if fallback_cash_account_id in emitted_cash_account_ids:
                continue
            account_records.append(
                await self._build_cash_account_balance_record(
                    portfolio=portfolio,
                    snapshot_row=cash_row,
                    resolved_as_of_date=resolved_as_of_date,
                    reporting_currency=reporting_currency,
                    cash_account_id=fallback_cash_account_id,
                    security_id=cash_row.snapshot.security_id,
                    instrument_name=(
                        cash_row.instrument.name
                        if cash_row.instrument is not None
                        else cash_row.snapshot.security_id
                    ),
                    account_currency=(
                        cash_row.instrument.currency
                        if cash_row.instrument and cash_row.instrument.currency
                        else portfolio.base_currency
                    ),
                )
            )

        account_records.sort(key=lambda row: (row.account_currency, row.cash_account_id))
        return account_records

    async def _build_cash_account_balance_record(
        self,
        *,
        portfolio: Any,
        snapshot_row: Any | None,
        resolved_as_of_date: date,
        reporting_currency: str,
        cash_account_id: str,
        security_id: str,
        instrument_name: str,
        account_currency: str,
    ) -> CashAccountBalanceRecord:
        if snapshot_row is None:
            native_balance = ZERO
            portfolio_balance = ZERO
        else:
            native_source_value = (
                snapshot_row.snapshot.market_value_local
                or snapshot_row.snapshot.market_value
                or ZERO
            )
            native_balance = Decimal(str(native_source_value))
            portfolio_balance = Decimal(str(snapshot_row.snapshot.market_value or ZERO))
        reporting_balance = await self._convert_amount(
            amount=portfolio_balance,
            from_currency=portfolio.base_currency,
            to_currency=reporting_currency,
            as_of_date=resolved_as_of_date,
        )
        return CashAccountBalanceRecord(
            cash_account_id=cash_account_id,
            instrument_id=security_id,
            security_id=security_id,
            account_currency=account_currency,
            instrument_name=instrument_name,
            balance_account_currency=native_balance,
            balance_portfolio_currency=portfolio_balance,
            balance_reporting_currency=reporting_balance,
        )

    @staticmethod
    def is_cash_row(row: Any) -> bool:
        return (
            row.instrument is not None
            and str(row.instrument.asset_class or "").upper() == CASH_ASSET_CLASS
        )

    @staticmethod
    def latest_snapshot_evidence_timestamp(rows: list[Any]) -> datetime | None:
        timestamps: list[datetime] = []
        for row in rows:
            snapshot = getattr(row, "snapshot", None)
            for candidate in (
                getattr(snapshot, "updated_at", None),
                getattr(snapshot, "created_at", None),
            ):
                if isinstance(candidate, datetime):
                    timestamps.append(candidate)
        return max(timestamps) if timestamps else None

    @staticmethod
    def data_quality_status(
        *,
        cash_rows: list[Any],
        account_records: list[CashAccountBalanceRecord],
    ) -> str:
        if not account_records:
            return UNKNOWN
        return COMPLETE if cash_rows else UNKNOWN


class CashBalanceService:
    def __init__(self, db: AsyncSession):
        self.repo = ReportingRepository(db)
        self._fx_cache: dict[tuple[str, str, date], Decimal] = {}
        self._resolver = CashBalanceResolver(repo=self.repo, convert_amount=self._convert_amount)

    async def get_cash_balances(
        self,
        *,
        portfolio_id: str,
        as_of_date: date | None = None,
        reporting_currency: str | None = None,
    ) -> CashBalancesResponse:
        portfolio = await self.repo.get_portfolio_by_id(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

        resolved_as_of_date = as_of_date or await self.repo.get_latest_business_date()
        if resolved_as_of_date is None:
            raise ValueError("No business date is available for cash balance queries.")
        effective_reporting_currency = reporting_currency or portfolio.base_currency

        rows = await self.repo.list_latest_snapshot_rows(
            portfolio_ids=[portfolio.portfolio_id],
            as_of_date=resolved_as_of_date,
        )
        return await self._resolver.build_cash_balances_response(
            portfolio=portfolio,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=effective_reporting_currency,
            rows=rows,
        )

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
