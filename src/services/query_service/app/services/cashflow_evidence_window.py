from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.financial.amounts import CurrencyCode, FxRate, MoneyAmount
from portfolio_common.domain.tenant import TenantId

from ..repositories.cashflow_repository import (
    CashflowFxRateEvidence,
    CashflowRepository,
    CashflowSeriesEvidence,
)

CASHFLOW_INTERMEDIATE_PRECISION = 50
CASHFLOW_ROUNDING_MODE = ROUND_HALF_EVEN


def cashflow_arithmetic_context() -> AbstractContextManager[Context]:
    """Own deterministic precision for conversion and downstream cashflow arithmetic."""

    return localcontext(
        Context(
            prec=CASHFLOW_INTERMEDIATE_PRECISION,
            rounding=CASHFLOW_ROUNDING_MODE,
        )
    )


@dataclass(frozen=True)
class CashflowEvidenceWindow:
    booked_rows: list[tuple[date, Decimal]]
    projected_rows: list[tuple[date, Decimal]]
    latest_evidence_timestamp: datetime | None
    booked_source_row_count: int
    projected_source_row_count: int
    booked_source_total: Decimal
    projected_source_total: Decimal
    booked_source_currency_totals: dict[str, Decimal]
    projected_source_currency_totals: dict[str, Decimal]
    native_booked_rows: list[tuple[date, str, Decimal]]
    native_projected_rows: list[tuple[date, str, Decimal]]
    fx_conversion_evidence: list[CashflowFxRateEvidence]


async def read_cashflow_evidence_window(
    *,
    repo: CashflowRepository,
    portfolio_id: str,
    portfolio_currency: str,
    start_date: date,
    end_date: date,
    include_projected: bool,
    tenant_id: TenantId,
) -> CashflowEvidenceWindow:
    booked_evidence = await repo.get_portfolio_cashflow_series_with_evidence(
        portfolio_id=portfolio_id,
        start_date=start_date,
        end_date=end_date,
        tenant_id=tenant_id,
    )
    if include_projected:
        projected_evidence = await repo.get_projected_settlement_cashflow_series_with_evidence(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
            tenant_id=tenant_id,
        )
        latest_projected_evidence = projected_evidence.latest_evidence_timestamp
        projected_source_row_count = projected_evidence.source_row_count
    else:
        projected_evidence = CashflowSeriesEvidence(rows=[], latest_evidence_timestamp=None)
        latest_projected_evidence = None
        projected_source_row_count = 0

    normalized_portfolio_currency = normalize_currency_code(portfolio_currency)
    native_booked_rows = booked_evidence.rows
    native_projected_rows = projected_evidence.rows
    required_conversions = {
        (currency, normalized_portfolio_currency, flow_date)
        for flow_date, currency, _amount in native_booked_rows + native_projected_rows
        if normalize_currency_code(currency) != normalized_portfolio_currency
    }
    fx_evidence_by_key = (
        await repo.get_cashflow_fx_rate_evidence(required_conversions=required_conversions)
        if required_conversions
        else {}
    )
    with cashflow_arithmetic_context():
        booked_rows = _convert_and_aggregate(
            rows=native_booked_rows,
            portfolio_currency=normalized_portfolio_currency,
            fx_evidence_by_key=fx_evidence_by_key,
        )
        projected_rows = _convert_and_aggregate(
            rows=native_projected_rows,
            portfolio_currency=normalized_portfolio_currency,
            fx_evidence_by_key=fx_evidence_by_key,
        )
        booked_source_total = sum((amount for _flow_date, amount in booked_rows), Decimal("0"))
        projected_source_total = sum(
            (amount for _flow_date, amount in projected_rows), Decimal("0")
        )

    return CashflowEvidenceWindow(
        booked_rows=booked_rows,
        projected_rows=projected_rows,
        booked_source_row_count=booked_evidence.source_row_count,
        projected_source_row_count=projected_source_row_count,
        booked_source_total=booked_source_total,
        projected_source_total=projected_source_total,
        booked_source_currency_totals=booked_evidence.source_currency_totals,
        projected_source_currency_totals=projected_evidence.source_currency_totals,
        native_booked_rows=native_booked_rows,
        native_projected_rows=native_projected_rows,
        fx_conversion_evidence=[fx_evidence_by_key[key] for key in sorted(fx_evidence_by_key)],
        latest_evidence_timestamp=max(
            (
                timestamp
                for timestamp in (
                    booked_evidence.latest_evidence_timestamp,
                    latest_projected_evidence,
                    *(item.source_updated_at for item in fx_evidence_by_key.values()),
                )
                if timestamp
            ),
            default=None,
        ),
    )


def _convert_and_aggregate(
    *,
    rows: list[tuple[date, str, Decimal]],
    portfolio_currency: str,
    fx_evidence_by_key: dict[tuple[str, str, date], CashflowFxRateEvidence],
) -> list[tuple[date, Decimal]]:
    totals: dict[date, Decimal] = {}
    target_currency = CurrencyCode.from_raw(portfolio_currency)
    for flow_date, raw_currency, raw_amount in rows:
        money = MoneyAmount.from_raw(amount=raw_amount, currency=raw_currency)
        if money.currency == target_currency:
            converted_amount = money.amount
        else:
            key = (money.currency.value, target_currency.value, flow_date)
            evidence = fx_evidence_by_key.get(key)
            if evidence is None:
                raise ValueError(
                    "Required exact-date direct FX conversion evidence is unavailable for "
                    f"{key[0]}/{key[1]} on {flow_date.isoformat()}."
                )
            converted_amount = money.converted(
                FxRate.from_raw(
                    from_currency=evidence.from_currency,
                    to_currency=evidence.to_currency,
                    rate=evidence.rate,
                    as_of_date=evidence.rate_date,
                )
            ).amount
        totals[flow_date] = totals.get(flow_date, Decimal("0")) + converted_amount
    return sorted(totals.items())
