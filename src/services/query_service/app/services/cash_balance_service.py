from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Awaitable, Callable, cast

from portfolio_common.reconciliation_quality import COMPLETE, UNKNOWN
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reporting_dto import CashAccountBalanceRecord, CashBalancesResponse, CashBalancesTotals
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.reporting_repository import ReportingRepository
from .control_code_normalization import normalize_control_code
from .decimal_amounts import decimal_or_zero
from .fx_conversion import CachedFxRateConverter
from .snapshot_evidence import latest_snapshot_evidence_timestamp

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
        portfolio_currency = normalize_currency_code(str(portfolio.base_currency))
        reporting_currency = normalize_currency_code(reporting_currency)
        cash_rows = [row for row in rows if self.is_cash_row(row)]
        account_records = await self.build_cash_account_balance_records(
            portfolio=portfolio,
            cash_rows=cash_rows,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
        )
        total_cash_portfolio_currency = sum(
            (record.balance_portfolio_currency for record in account_records),
            ZERO,
        )
        total_cash_reporting_currency = sum(
            (record.balance_reporting_currency for record in account_records),
            ZERO,
        )
        cash_weight_evidence = _source_reported_cash_weight_evidence(
            total_cash_portfolio_currency=total_cash_portfolio_currency,
            rows=rows,
            resolved_as_of_date=resolved_as_of_date,
        )
        return CashBalancesResponse(
            portfolio_id=portfolio.portfolio_id,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            resolved_as_of_date=resolved_as_of_date,
            totals=CashBalancesTotals(
                cash_account_count=len(account_records),
                total_balance_portfolio_currency=total_cash_portfolio_currency,
                total_balance_reporting_currency=total_cash_reporting_currency,
                source_reported_cash_weight=(cash_weight_evidence.source_reported_cash_weight),
                source_reported_cash_weight_denominator_portfolio_currency=(
                    cash_weight_evidence.denominator_portfolio_currency
                ),
                source_reported_cash_weight_supportability=cash_weight_evidence.supportability,
            ),
            cash_accounts=account_records,
            **source_data_product_runtime_metadata(
                as_of_date=resolved_as_of_date,
                data_quality_status=self.data_quality_status(
                    cash_rows=cash_rows,
                    account_records=account_records,
                ),
                latest_evidence_timestamp=latest_snapshot_evidence_timestamp(cash_rows),
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
        master_rows = await self.repo.list_cash_account_masters(
            portfolio_id=portfolio.portfolio_id,
            as_of_date=resolved_as_of_date,
        )
        master_by_security_id = _master_rows_by_security_id(master_rows)
        fallback_cash_account_ids = await self._fallback_cash_account_ids(
            portfolio_id=portfolio.portfolio_id,
            cash_rows=cash_rows,
            master_by_security_id=master_by_security_id,
            resolved_as_of_date=resolved_as_of_date,
        )
        record_inputs = _cash_account_record_inputs(
            portfolio=portfolio,
            master_rows=master_rows,
            master_by_security_id=master_by_security_id,
            cash_rows=cash_rows,
            fallback_cash_account_ids=fallback_cash_account_ids,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
        )
        account_records = [
            await self._build_cash_account_balance_record(**record_input)
            for record_input in record_inputs
        ]

        account_records.sort(key=lambda row: (row.account_currency, row.cash_account_id))
        return account_records

    async def _fallback_cash_account_ids(
        self,
        *,
        portfolio_id: str,
        cash_rows: list[Any],
        master_by_security_id: dict[str, Any],
        resolved_as_of_date: date,
    ) -> dict[str, str]:
        fallback_security_ids = _fallback_security_ids(
            cash_rows=cash_rows,
            master_by_security_id=master_by_security_id,
        )
        if not fallback_security_ids:
            return {}
        fallback_rows = await self.repo.get_latest_cash_account_ids(
            portfolio_id=portfolio_id,
            cash_security_ids=fallback_security_ids,
            as_of_date=resolved_as_of_date,
        )
        return _normalized_cash_account_ids(fallback_rows)

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
        account_currency = normalize_currency_code(str(account_currency))
        if snapshot_row is None:
            native_balance = ZERO
            portfolio_balance = ZERO
        else:
            native_source_value = (
                snapshot_row.snapshot.market_value_local
                or snapshot_row.snapshot.market_value
                or ZERO
            )
            native_balance = decimal_or_zero(native_source_value)
            portfolio_balance = decimal_or_zero(snapshot_row.snapshot.market_value)
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
            and normalize_control_code(row.instrument.asset_class) == CASH_ASSET_CLASS
        )

    @staticmethod
    def data_quality_status(
        *,
        cash_rows: list[Any],
        account_records: list[CashAccountBalanceRecord],
    ) -> str:
        if not account_records:
            return cast(str, UNKNOWN)
        return cast(str, COMPLETE if cash_rows else UNKNOWN)


def _cash_security_ids(cash_rows: list[Any]) -> list[str]:
    return [
        security_id
        for row in cash_rows
        if (security_id := normalize_security_id(row.snapshot.security_id))
    ]


def _master_rows_by_security_id(master_rows: list[Any]) -> dict[str, Any]:
    return {
        security_id: row
        for row in master_rows
        if (security_id := normalize_security_id(row.security_id))
    }


def _fallback_security_ids(
    *,
    cash_rows: list[Any],
    master_by_security_id: dict[str, Any],
) -> list[str]:
    return [
        security_id
        for security_id in dict.fromkeys(_cash_security_ids(cash_rows))
        if security_id not in master_by_security_id
    ]


def _normalized_cash_account_ids(cash_account_id_rows: dict[str, str]) -> dict[str, str]:
    normalized_rows: dict[str, str] = {}
    for security_id, cash_account_id in cash_account_id_rows.items():
        normalized_security_id = normalize_security_id(security_id)
        if normalized_security_id:
            normalized_rows[normalized_security_id] = cash_account_id
    return normalized_rows


def _snapshot_rows_by_security_id(cash_rows: list[Any]) -> dict[str, Any]:
    return {
        security_id: row
        for row in cash_rows
        if (security_id := normalize_security_id(row.snapshot.security_id))
    }


@dataclass(frozen=True)
class _CashWeightEvidence:
    source_reported_cash_weight: Decimal | None
    denominator_portfolio_currency: Decimal | None
    supportability: str


def _source_reported_cash_weight_evidence(
    *,
    total_cash_portfolio_currency: Decimal,
    rows: list[Any],
    resolved_as_of_date: date,
) -> _CashWeightEvidence:
    denominator = sum((decimal_or_zero(row.snapshot.market_value) for row in rows), ZERO)
    blocked_supportability = _blocked_cash_weight_supportability(
        rows=rows,
        resolved_as_of_date=resolved_as_of_date,
        denominator=denominator,
    )
    if blocked_supportability is not None:
        return _blocked_cash_weight(blocked_supportability)
    return _CashWeightEvidence(
        source_reported_cash_weight=total_cash_portfolio_currency / denominator,
        denominator_portfolio_currency=denominator,
        supportability="SUPPORTED",
    )


def _blocked_cash_weight_supportability(
    *,
    rows: list[Any],
    resolved_as_of_date: date,
    denominator: Decimal,
) -> str | None:
    if not rows:
        return "BLOCKED_MISSING_DENOMINATOR"
    if any(row.snapshot.date != resolved_as_of_date for row in rows):
        return "BLOCKED_STALE_DENOMINATOR"
    if denominator <= ZERO:
        return "BLOCKED_ZERO_DENOMINATOR"
    return None


def _blocked_cash_weight(supportability: str) -> _CashWeightEvidence:
    return _CashWeightEvidence(
        source_reported_cash_weight=None,
        denominator_portfolio_currency=None,
        supportability=supportability,
    )


def _master_record_input(
    *,
    portfolio: Any,
    master_row: Any,
    snapshot_row: Any | None,
    resolved_as_of_date: date,
    reporting_currency: str,
) -> dict[str, Any]:
    security_id = normalize_security_id(master_row.security_id)
    return {
        "portfolio": portfolio,
        "snapshot_row": snapshot_row,
        "resolved_as_of_date": resolved_as_of_date,
        "reporting_currency": reporting_currency,
        "cash_account_id": master_row.cash_account_id,
        "security_id": security_id,
        "instrument_name": _master_instrument_name(
            master_row=master_row,
            snapshot_row=snapshot_row,
        ),
        "account_currency": master_row.account_currency,
    }


def _master_instrument_name(*, master_row: Any, snapshot_row: Any | None) -> str:
    if snapshot_row and snapshot_row.instrument:
        return cast(str, snapshot_row.instrument.name)
    return cast(str, master_row.display_name)


def _cash_row_record_input(
    *,
    portfolio: Any,
    cash_row: Any,
    cash_account_id: str,
    security_id: str,
    resolved_as_of_date: date,
    reporting_currency: str,
) -> dict[str, Any]:
    return {
        "portfolio": portfolio,
        "snapshot_row": cash_row,
        "resolved_as_of_date": resolved_as_of_date,
        "reporting_currency": reporting_currency,
        "cash_account_id": cash_account_id,
        "security_id": security_id,
        "instrument_name": _cash_row_instrument_name(
            cash_row=cash_row,
            security_id=security_id,
        ),
        "account_currency": _cash_row_account_currency(
            cash_row=cash_row,
            portfolio=portfolio,
        ),
    }


def _cash_row_instrument_name(*, cash_row: Any, security_id: str) -> str:
    if cash_row.instrument is not None:
        return cast(str, cash_row.instrument.name)
    return security_id


def _cash_row_account_currency(*, cash_row: Any, portfolio: Any) -> str:
    if cash_row.instrument and cash_row.instrument.currency:
        return cast(str, cash_row.instrument.currency)
    return cast(str, portfolio.base_currency)


def _cash_row_account_id(
    *,
    security_id: str,
    master_by_security_id: dict[str, Any],
    fallback_cash_account_ids: dict[str, str],
) -> str:
    master_row = master_by_security_id.get(security_id)
    if master_row is not None:
        return cast(str, master_row.cash_account_id)
    return fallback_cash_account_ids.get(security_id) or security_id


def _cash_account_record_inputs(
    *,
    portfolio: Any,
    master_rows: list[Any],
    master_by_security_id: dict[str, Any],
    cash_rows: list[Any],
    fallback_cash_account_ids: dict[str, str],
    resolved_as_of_date: date,
    reporting_currency: str,
) -> list[dict[str, Any]]:
    snapshot_by_security_id = _snapshot_rows_by_security_id(cash_rows)
    record_inputs = _master_record_inputs(
        portfolio=portfolio,
        master_rows=master_rows,
        snapshot_by_security_id=snapshot_by_security_id,
        resolved_as_of_date=resolved_as_of_date,
        reporting_currency=reporting_currency,
    )
    emitted_cash_account_ids = {record_input["cash_account_id"] for record_input in record_inputs}
    record_inputs.extend(
        _fallback_record_inputs(
            portfolio=portfolio,
            cash_rows=cash_rows,
            master_by_security_id=master_by_security_id,
            fallback_cash_account_ids=fallback_cash_account_ids,
            emitted_cash_account_ids=emitted_cash_account_ids,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
        )
    )
    return record_inputs


def _master_record_inputs(
    *,
    portfolio: Any,
    master_rows: list[Any],
    snapshot_by_security_id: dict[str, Any],
    resolved_as_of_date: date,
    reporting_currency: str,
) -> list[dict[str, Any]]:
    return [
        _master_record_input(
            portfolio=portfolio,
            master_row=master_row,
            snapshot_row=snapshot_by_security_id.get(normalize_security_id(master_row.security_id)),
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
        )
        for master_row in master_rows
    ]


def _fallback_record_inputs(
    *,
    portfolio: Any,
    cash_rows: list[Any],
    master_by_security_id: dict[str, Any],
    fallback_cash_account_ids: dict[str, str],
    emitted_cash_account_ids: set[str],
    resolved_as_of_date: date,
    reporting_currency: str,
) -> list[dict[str, Any]]:
    record_inputs: list[dict[str, Any]] = []
    for cash_row in cash_rows:
        security_id = normalize_security_id(cash_row.snapshot.security_id)
        cash_account_id = _cash_row_account_id(
            security_id=security_id,
            master_by_security_id=master_by_security_id,
            fallback_cash_account_ids=fallback_cash_account_ids,
        )
        if cash_account_id in emitted_cash_account_ids:
            continue
        record_inputs.append(
            _cash_row_record_input(
                portfolio=portfolio,
                cash_row=cash_row,
                cash_account_id=cash_account_id,
                security_id=security_id,
                resolved_as_of_date=resolved_as_of_date,
                reporting_currency=reporting_currency,
            )
        )
        emitted_cash_account_ids.add(cash_account_id)
    return record_inputs


class CashBalanceService:
    def __init__(self, db: AsyncSession):
        self.repo = ReportingRepository(db)
        self._fx_converter = CachedFxRateConverter(self.repo)
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
        resolved_as_of_date = (
            await self.repo.get_latest_business_date() if as_of_date is None else as_of_date
        )

        if resolved_as_of_date is None:
            raise ValueError("No business date is available for cash balance queries.")
        effective_reporting_currency = reporting_currency or portfolio.base_currency
        effective_reporting_currency = normalize_currency_code(str(effective_reporting_currency))

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
