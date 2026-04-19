from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.demo_data_pack import (  # noqa: E402
    DEFAULT_DEMO_BENCHMARK_ID,
    _build_benchmark_reference_data,
    _request_json,
    _wait_ready,
    build_risk_free_reference_data,
)
from tools.front_office_seed_contract import (  # noqa: E402
    FrontOfficeSeedContract,
    load_front_office_seed_contract,
)

LOGGER = logging.getLogger("front_office_portfolio_seed")
FRONT_OFFICE_SEED_CONTRACT = load_front_office_seed_contract()
DEFAULT_PORTFOLIO_ID = FRONT_OFFICE_SEED_CONTRACT.portfolio_id
DEFAULT_BENCHMARK_ID = FRONT_OFFICE_SEED_CONTRACT.benchmark_id
DEFAULT_POSTGRES_CONTAINER = "lotus-core-app-local-postgres-1"
DEFAULT_BENCHMARK_COMPONENT_INDEX_IDS = (
    "IDX_GLOBAL_EQUITY_TR",
    "IDX_GLOBAL_BOND_TR",
)


@dataclass(frozen=True)
class FrontOfficePortfolioExpectation:
    portfolio_id: str
    min_positions: int
    min_valued_positions: int
    min_transactions: int
    min_cash_accounts: int
    min_allocation_views: int
    min_projected_cashflow_points: int


def _build_front_office_expectation(
    contract: FrontOfficeSeedContract,
) -> FrontOfficePortfolioExpectation:
    return FrontOfficePortfolioExpectation(
        portfolio_id=contract.portfolio_id,
        min_positions=contract.min_positions,
        min_valued_positions=contract.min_valued_positions,
        min_transactions=contract.min_transactions,
        min_cash_accounts=contract.min_cash_accounts,
        min_allocation_views=contract.min_allocation_views,
        min_projected_cashflow_points=contract.min_projected_cashflow_points,
    )


FRONT_OFFICE_EXPECTATION = _build_front_office_expectation(FRONT_OFFICE_SEED_CONTRACT)

INCOME_SUMMARY_TRANSACTION_TYPES = frozenset({"DIVIDEND", "INTEREST", "CASH_IN_LIEU"})
ACTIVITY_SUMMARY_BUCKET_BY_TRANSACTION_TYPE = {
    "DEPOSIT": "INFLOWS",
    "TRANSFER_IN": "INFLOWS",
    "WITHDRAWAL": "OUTFLOWS",
    "TRANSFER_OUT": "OUTFLOWS",
    "FEE": "FEES",
    "TAX": "TAXES",
}


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _derive_reporting_summary_signals(
    *,
    transactions: list[dict[str, Any]],
    start_date: str,
    end_date: str,
) -> tuple[list[str], list[str]]:
    requested_start = date.fromisoformat(start_date)
    requested_end = date.fromisoformat(end_date)
    income_types: set[str] = set()
    activity_buckets: set[str] = set()

    for transaction in transactions:
        transaction_timestamp = _parse_iso_datetime(transaction.get("transaction_date"))
        if transaction_timestamp is None:
            continue
        transaction_date = transaction_timestamp.date()
        if transaction_date < requested_start or transaction_date > requested_end:
            continue

        transaction_type = str(transaction.get("transaction_type", "")).upper()
        if transaction_type in INCOME_SUMMARY_TRANSACTION_TYPES:
            income_types.add(transaction_type)

        bucket = ACTIVITY_SUMMARY_BUCKET_BY_TRANSACTION_TYPE.get(transaction_type)
        if bucket:
            activity_buckets.add(bucket)

        withholding_tax_amount = transaction.get("withholding_tax_amount")
        if withholding_tax_amount not in (None, "", 0, "0", "0.0", "0.00", "0E-10"):
            if Decimal(str(withholding_tax_amount)) != 0:
                activity_buckets.add("TAXES")

    return sorted(income_types), sorted(activity_buckets)


def build_portfolio_seed_cleanup_sql(*, portfolio_id: str) -> str:
    """
    Build the destructive local reseed cleanup SQL for the canonical front-office seed.

    This cleanup stays scoped to portfolio-owned rows only. If a local Docker-backed runtime has
    stale shared Kafka, idempotency, or replay state from a prior load or performance run, reset
    the lotus-core Docker state before reseeding instead of deleting shared runtime tables from the
    front-office seed tool.
    """
    return "\n".join(
        [
            (
                "delete from financial_reconciliation_findings "
                f"where portfolio_id = '{portfolio_id}';"
            ),
            (f"delete from financial_reconciliation_runs where portfolio_id = '{portfolio_id}';"),
            f"delete from simulation_changes where portfolio_id = '{portfolio_id}';",
            f"delete from simulation_sessions where portfolio_id = '{portfolio_id}';",
            f"delete from analytics_export_jobs where portfolio_id = '{portfolio_id}';",
            f"delete from portfolio_aggregation_jobs where portfolio_id = '{portfolio_id}';",
            f"delete from portfolio_valuation_jobs where portfolio_id = '{portfolio_id}';",
            f"delete from daily_position_snapshots where portfolio_id = '{portfolio_id}';",
            f"delete from portfolio_timeseries where portfolio_id = '{portfolio_id}';",
            f"delete from position_timeseries where portfolio_id = '{portfolio_id}';",
            f"delete from position_history where portfolio_id = '{portfolio_id}';",
            f"delete from position_state where portfolio_id = '{portfolio_id}';",
            f"delete from position_lot_state where portfolio_id = '{portfolio_id}';",
            f"delete from accrued_income_offset_state where portfolio_id = '{portfolio_id}';",
            f"delete from cashflows where portfolio_id = '{portfolio_id}';",
            (
                "delete from transaction_costs where transaction_id in "
                f"(select transaction_id from transactions where portfolio_id = '{portfolio_id}');"
            ),
            f"delete from pipeline_stage_state where portfolio_id = '{portfolio_id}';",
            f"delete from processed_events where portfolio_id = '{portfolio_id}';",
            f"delete from cash_account_masters where portfolio_id = '{portfolio_id}';",
            f"delete from portfolio_benchmark_assignments where portfolio_id = '{portfolio_id}';",
            f"delete from transactions where portfolio_id = '{portfolio_id}';",
            f"delete from instruments where portfolio_id = '{portfolio_id}';",
            f"delete from portfolios where portfolio_id = '{portfolio_id}';",
        ]
    )


def build_front_office_seed_cleanup_sql(*, portfolio_id: str, benchmark_id: str) -> str:
    benchmark_index_id_list = ", ".join(
        f"'{index_id}'" for index_id in DEFAULT_BENCHMARK_COMPONENT_INDEX_IDS
    )
    return "\n".join(
        [
            build_portfolio_seed_cleanup_sql(portfolio_id=portfolio_id),
            f"delete from benchmark_composition_series where benchmark_id = '{benchmark_id}';",
            f"delete from benchmark_return_series where benchmark_id = '{benchmark_id}';",
            f"delete from benchmark_definitions where benchmark_id = '{benchmark_id}';",
            f"delete from index_price_series where index_id in ({benchmark_index_id_list});",
            f"delete from index_return_series where index_id in ({benchmark_index_id_list});",
            f"delete from index_definitions where index_id in ({benchmark_index_id_list});",
        ]
    )


def _business_dates(start: date, end: date) -> list[str]:
    dates: list[str] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _calendar_dates(start: date, end: date) -> list[str]:
    dates: list[str] = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _iso_utc_timestamp(day: date, hour: int = 21) -> str:
    return (
        datetime(day.year, day.month, day.day, hour=hour, tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _interpolate_prices(
    *,
    dates: list[str],
    start_price: Decimal,
    end_price: Decimal,
    precision: str = "0.0001",
) -> list[str]:
    if len(dates) <= 1:
        return [format(end_price.quantize(Decimal(precision)), "f")] * len(dates)
    step_count = Decimal(len(dates) - 1)
    values: list[str] = []
    for index, _current in enumerate(dates):
        weight = Decimal(index) / step_count
        price = start_price + ((end_price - start_price) * weight)
        values.append(format(price.quantize(Decimal(precision)), "f"))
    return values


def _invert_rate(rate: str, precision: str = "0.000001") -> str:
    return format((Decimal("1") / Decimal(rate)).quantize(Decimal(precision)), "f")


def _tx(
    tx_id: str,
    *,
    portfolio_id: str,
    instrument_id: str,
    security_id: str,
    when: datetime,
    tx_type: str,
    quantity: str,
    price: str,
    gross: str,
    trade_currency: str,
    settlement_date: datetime | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "transaction_id": tx_id,
        "portfolio_id": portfolio_id,
        "instrument_id": instrument_id,
        "security_id": security_id,
        "transaction_date": when.isoformat().replace("+00:00", "Z"),
        "transaction_type": tx_type,
        "quantity": quantity,
        "price": price,
        "gross_transaction_amount": gross,
        "trade_currency": trade_currency,
        "currency": trade_currency,
    }
    if settlement_date is not None:
        payload["settlement_date"] = settlement_date.isoformat().replace("+00:00", "Z")
    payload.update(extra)
    return payload


def _cash_tx(
    tx_id: str,
    *,
    portfolio_id: str,
    instrument_id: str,
    security_id: str,
    when: datetime,
    tx_type: str,
    gross: str,
    trade_currency: str,
    settlement_date: datetime | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return _tx(
        tx_id,
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        security_id=security_id,
        when=when,
        tx_type=tx_type,
        quantity=gross,
        price="1",
        gross=gross,
        trade_currency=trade_currency,
        settlement_date=settlement_date,
        **extra,
    )


def _paired_internal_leg_metadata(*, portfolio_id: str, event_code: str) -> dict[str, str]:
    normalized_code = event_code.strip().upper().replace(" ", "-")
    return {
        "economic_event_id": f"EVT-{portfolio_id}-{normalized_code}",
        "linked_transaction_group_id": f"LTG-{portfolio_id}-{normalized_code}",
    }


def _expected_internal_pair_net_amount(product_leg: dict[str, Any]) -> Decimal:
    tx_type = str(product_leg["transaction_type"]).upper()
    gross_amount = Decimal(str(product_leg["gross_transaction_amount"]))

    if tx_type == "BUY":
        return gross_amount
    if tx_type in {"SELL", "DIVIDEND"}:
        return -gross_amount
    if tx_type == "INTEREST":
        net_interest_amount = product_leg.get("net_interest_amount")
        if net_interest_amount is not None:
            return -Decimal(str(net_interest_amount))
        withholding_tax_amount = Decimal(str(product_leg.get("withholding_tax_amount", "0")))
        other_deductions_amount = Decimal(
            str(product_leg.get("other_interest_deductions_amount", "0"))
        )
        return -(gross_amount - withholding_tax_amount - other_deductions_amount)
    raise ValueError(f"Unsupported paired product transaction type: {tx_type}")


def _cash_leg_signed_amount(cash_leg: dict[str, Any]) -> Decimal:
    tx_type = str(cash_leg["transaction_type"]).upper()
    gross_amount = Decimal(str(cash_leg["gross_transaction_amount"]))
    if tx_type == "BUY":
        return gross_amount
    if tx_type == "SELL":
        return -gross_amount
    raise ValueError(f"Unsupported paired cash transaction type: {tx_type}")


def _validate_front_office_cash_transactions(transactions: list[dict[str, Any]]) -> None:
    for transaction in transactions:
        if not str(transaction.get("security_id", "")).startswith("CASH_"):
            continue

        tx_type = str(transaction.get("transaction_type", "")).upper()
        if tx_type not in {"BUY", "SELL", "DEPOSIT", "WITHDRAWAL", "FEE"}:
            continue

        transaction_id = str(transaction["transaction_id"])
        quantity = Decimal(str(transaction["quantity"]))
        price = Decimal(str(transaction["price"]))
        gross = Decimal(str(transaction["gross_transaction_amount"]))
        currency = str(transaction["currency"])
        trade_currency = str(transaction["trade_currency"])

        if price != Decimal("1"):
            raise ValueError(f"{transaction_id} must use price=1 for cash-book transaction rows.")
        if quantity != gross:
            raise ValueError(
                f"{transaction_id} must use quantity equal to gross_transaction_amount "
                "for cash-book transaction rows."
            )
        if currency != trade_currency:
            raise ValueError(
                f"{transaction_id} must use matching currency and trade_currency "
                "for cash-book transaction rows."
            )


def _validate_front_office_internal_transaction_pairs(
    transactions: list[dict[str, Any]],
) -> None:
    paired_transaction_ids = (
        ("TXN-BUY-AAPL-001", "TXN-CASH-BUY-AAPL-001"),
        ("TXN-BUY-MSFT-001", "TXN-CASH-BUY-MSFT-001"),
        ("TXN-BUY-SAP-001", "TXN-CASH-BUY-SAP-001"),
        ("TXN-BUY-WORLD-ETF-001", "TXN-CASH-BUY-WORLD-ETF-001"),
        ("TXN-BUY-BLK-ALLOC-001", "TXN-CASH-BUY-BLK-ALLOC-001"),
        ("TXN-BUY-PIMCO-INC-001", "TXN-CASH-BUY-PIMCO-INC-001"),
        ("TXN-BUY-UST-001", "TXN-CASH-BUY-UST-001"),
        ("TXN-BUY-SIEMENS-BOND-001", "TXN-CASH-BUY-SIEMENS-BOND-001"),
        ("TXN-BUY-PRIVCREDIT-001", "TXN-CASH-BUY-PRIVCREDIT-001"),
        ("TXN-SELL-AAPL-001", "TXN-CASH-SELL-AAPL-001"),
        ("TXN-DIV-AAPL-001", "TXN-CASH-DIV-AAPL-001"),
        ("TXN-INT-UST-001", "TXN-CASH-INT-UST-001"),
    )
    transactions_by_id = {
        str(transaction["transaction_id"]): transaction for transaction in transactions
    }

    for product_transaction_id, cash_transaction_id in paired_transaction_ids:
        product_leg = transactions_by_id[product_transaction_id]
        cash_leg = transactions_by_id[cash_transaction_id]

        if product_leg.get("economic_event_id") != cash_leg.get("economic_event_id"):
            raise ValueError(
                f"{product_transaction_id} and {cash_transaction_id} must share economic_event_id."
            )
        if product_leg.get("linked_transaction_group_id") != cash_leg.get(
            "linked_transaction_group_id"
        ):
            raise ValueError(
                f"{product_transaction_id} and {cash_transaction_id} must share "
                "linked_transaction_group_id."
            )
        if str(product_leg["trade_currency"]) != str(cash_leg["trade_currency"]):
            raise ValueError(
                f"{product_transaction_id} and {cash_transaction_id} must share trade_currency."
            )

        product_signed_amount = _expected_internal_pair_net_amount(product_leg)
        cash_signed_amount = _cash_leg_signed_amount(cash_leg)
        if product_signed_amount + cash_signed_amount != Decimal("0"):
            raise ValueError(
                f"{product_transaction_id} and {cash_transaction_id} must economically net to "
                "zero across product and cash legs."
            )


def build_front_office_portfolio_bundle(
    *,
    portfolio_id: str,
    start_date: date,
    end_date: date,
    benchmark_start_date: date | None = None,
    benchmark_id: str = DEFAULT_BENCHMARK_ID,
) -> dict[str, Any]:
    effective_benchmark_start = benchmark_start_date or start_date
    business_dates = _business_dates(start_date, end_date)
    calendar_dates = _calendar_dates(start_date, end_date)
    fx_calendar_dates = _calendar_dates(start_date, end_date + timedelta(days=30))
    as_of_date = end_date.isoformat()
    forward_withdrawal_date = end_date + timedelta(days=7)
    forward_withdrawal_settlement_date = end_date + timedelta(days=10)

    def tx_dt(day_offset: int, hour: int = 10) -> datetime:
        current = start_date + timedelta(days=day_offset)
        return datetime(
            current.year,
            current.month,
            current.day,
            hour,
            0,
            0,
            tzinfo=UTC,
        )

    def date_dt(current: date, hour: int = 10) -> datetime:
        return datetime(
            current.year,
            current.month,
            current.day,
            hour,
            0,
            0,
            tzinfo=UTC,
        )

    def settle(day_offset: int, lag_days: int = 2) -> datetime:
        current = start_date + timedelta(days=day_offset + lag_days)
        return datetime(
            current.year,
            current.month,
            current.day,
            16,
            0,
            0,
            tzinfo=UTC,
        )

    eur_usd = _interpolate_prices(
        dates=fx_calendar_dates,
        start_price=Decimal("1.072500"),
        end_price=Decimal("1.110000"),
        precision="0.000001",
    )
    eur_usd_by_date = dict(zip(fx_calendar_dates, eur_usd, strict=True))

    def fx_rate_for_transaction(
        when: datetime,
        *,
        from_currency: str,
        to_currency: str = "USD",
    ) -> str:
        transaction_date = when.date().isoformat()
        if from_currency == to_currency:
            return "1.000000"
        if from_currency == "EUR" and to_currency == "USD":
            return eur_usd_by_date[transaction_date]
        if from_currency == "USD" and to_currency == "EUR":
            return _invert_rate(eur_usd_by_date[transaction_date])
        raise ValueError(
            f"Unsupported transaction FX pair for front-office seed: {from_currency}/{to_currency}"
        )

    portfolios = [
        {
            "portfolio_id": portfolio_id,
            "base_currency": "USD",
            "open_date": "2025-01-06",
            "risk_exposure": "balanced",
            "investment_time_horizon": "long_term",
            "portfolio_type": "discretionary",
            "objective": "Long-term real wealth growth with controlled income and liquidity.",
            "booking_center_code": "Singapore",
            "client_id": "CIF_SG_000184",
            "advisor_id": "RM_SG_001",
            "status": "active",
            "cost_basis_method": "FIFO",
            "is_leverage_allowed": False,
        }
    ]

    instruments = [
        {
            "security_id": "CASH_USD_BOOK_OPERATING",
            "name": "USD Operating Cash",
            "isin": "CASH-USD-OPERATING-001",
            "currency": "USD",
            "product_type": "Cash",
            "asset_class": "Cash",
            "issuer_id": "CASH_LEDGER",
            "issuer_name": "Custody Cash Ledger",
            "ultimate_parent_issuer_id": "CASH_LEDGER",
            "ultimate_parent_issuer_name": "Custody Cash Ledger",
            "liquidity_tier": "L1",
        },
        {
            "security_id": "CASH_EUR_BOOK_OPERATING",
            "name": "EUR Operating Cash",
            "isin": "CASH-EUR-OPERATING-001",
            "currency": "EUR",
            "product_type": "Cash",
            "asset_class": "Cash",
            "issuer_id": "CASH_LEDGER",
            "issuer_name": "Custody Cash Ledger",
            "ultimate_parent_issuer_id": "CASH_LEDGER",
            "ultimate_parent_issuer_name": "Custody Cash Ledger",
            "liquidity_tier": "L1",
        },
        {
            "security_id": "FO_EQ_AAPL_US",
            "name": "Apple Inc.",
            "isin": "FOUS0378331005",
            "currency": "USD",
            "product_type": "Equity",
            "asset_class": "Equity",
            "sector": "Information Technology",
            "country_of_risk": "United States",
            "issuer_id": "ISSUER_AAPL",
            "issuer_name": "Apple Inc.",
            "ultimate_parent_issuer_id": "ISSUER_AAPL",
            "ultimate_parent_issuer_name": "Apple Inc.",
            "liquidity_tier": "L1",
        },
        {
            "security_id": "FO_EQ_MSFT_US",
            "name": "Microsoft Corporation",
            "isin": "FOUS5949181045",
            "currency": "USD",
            "product_type": "Equity",
            "asset_class": "Equity",
            "sector": "Information Technology",
            "country_of_risk": "United States",
            "issuer_id": "ISSUER_MSFT",
            "issuer_name": "Microsoft Corporation",
            "ultimate_parent_issuer_id": "ISSUER_MSFT",
            "ultimate_parent_issuer_name": "Microsoft Corporation",
            "liquidity_tier": "L1",
        },
        {
            "security_id": "FO_EQ_SAP_DE",
            "name": "SAP SE",
            "isin": "FODE0007164600",
            "currency": "EUR",
            "product_type": "Equity",
            "asset_class": "Equity",
            "sector": "Information Technology",
            "country_of_risk": "Germany",
            "issuer_id": "ISSUER_SAP",
            "issuer_name": "SAP SE",
            "ultimate_parent_issuer_id": "ISSUER_SAP",
            "ultimate_parent_issuer_name": "SAP SE",
            "liquidity_tier": "L1",
        },
        {
            "security_id": "FO_ETF_MSCI_WORLD",
            "name": "iShares Core MSCI World UCITS ETF",
            "isin": "FOIE00B4L5Y983",
            "currency": "USD",
            "product_type": "ETF",
            "asset_class": "Equity",
            "sector": "Multi-Asset",
            "country_of_risk": "Ireland",
            "issuer_id": "ISSUER_ISHARES",
            "issuer_name": "BlackRock Asset Management Ireland Limited",
            "ultimate_parent_issuer_id": "ULTIMATE_BLACKROCK",
            "ultimate_parent_issuer_name": "BlackRock, Inc.",
            "liquidity_tier": "L1",
        },
        {
            "security_id": "FO_FUND_BLK_ALLOC",
            "name": "BlackRock Global Allocation Fund",
            "isin": "FOLU0171301533",
            "currency": "EUR",
            "product_type": "Fund",
            "asset_class": "Fund",
            "sector": "Multi-Asset",
            "country_of_risk": "Luxembourg",
            "issuer_id": "ISSUER_BLACKROCK_GAF",
            "issuer_name": "BlackRock Global Funds",
            "ultimate_parent_issuer_id": "ULTIMATE_BLACKROCK",
            "ultimate_parent_issuer_name": "BlackRock, Inc.",
            "liquidity_tier": "L2",
        },
        {
            "security_id": "FO_FUND_PIMCO_INC",
            "name": "PIMCO GIS Income Fund",
            "isin": "FOIE00B11XZ103",
            "currency": "USD",
            "product_type": "Fund",
            "asset_class": "Fund",
            "sector": "Fixed Income",
            "country_of_risk": "Ireland",
            "issuer_id": "ISSUER_PIMCO_GIS",
            "issuer_name": "PIMCO Global Advisors (Ireland) Limited",
            "ultimate_parent_issuer_id": "ULTIMATE_PIMCO",
            "ultimate_parent_issuer_name": "Pacific Investment Management Company LLC",
            "liquidity_tier": "L3",
        },
        {
            "security_id": "FO_BOND_UST_2030",
            "name": "United States Treasury 3.875% 2030",
            "isin": "FOUS91282CHP95",
            "currency": "USD",
            "product_type": "Bond",
            "asset_class": "Fixed Income",
            "sector": "Government",
            "country_of_risk": "United States",
            "rating": "AA+",
            "maturity_date": "2030-02-15",
            "issuer_id": "ISSUER_UST",
            "issuer_name": "United States Treasury",
            "ultimate_parent_issuer_id": "ISSUER_UST",
            "ultimate_parent_issuer_name": "United States Treasury",
            "liquidity_tier": "L1",
        },
        {
            "security_id": "FO_BOND_SIEMENS_2031",
            "name": "Siemens Financieringsmaatschappij NV 2.500% 2031",
            "isin": "FOXS2671347285",
            "currency": "EUR",
            "product_type": "Bond",
            "asset_class": "Fixed Income",
            "sector": "Industrials",
            "country_of_risk": "Netherlands",
            "rating": "A",
            "maturity_date": "2031-09-04",
            "issuer_id": "ISSUER_SIEMENS_FINANCE",
            "issuer_name": "Siemens Financieringsmaatschappij NV",
            "ultimate_parent_issuer_id": "ULTIMATE_SIEMENS",
            "ultimate_parent_issuer_name": "Siemens AG",
            "liquidity_tier": "L2",
        },
        {
            "security_id": "FO_PRIV_PRIVATE_CREDIT_A",
            "name": "Private Credit Opportunities Fund A",
            "isin": "FOIE000PRIVCRED1",
            "currency": "USD",
            "product_type": "Fund",
            "asset_class": "Fund",
            "sector": "Private Credit",
            "country_of_risk": "Ireland",
            "issuer_id": "ISSUER_PRIVCREDIT",
            "issuer_name": "Private Credit Opportunities Platform",
            "ultimate_parent_issuer_id": "ULTIMATE_PRIVCREDIT",
            "ultimate_parent_issuer_name": "Private Credit Opportunities Platform",
            "liquidity_tier": "L5",
        },
    ]

    cash_accounts = [
        {
            "cash_account_id": "CASH-ACC-USD-001",
            "portfolio_id": portfolio_id,
            "security_id": "CASH_USD_BOOK_OPERATING",
            "display_name": "USD Operating Cash",
            "account_currency": "USD",
            "account_role": "OPERATING_CASH",
            "lifecycle_status": "ACTIVE",
            "opened_on": "2025-01-06",
            "source_system": "LOTUS_FRONT_OFFICE_SEED",
            "source_record_id": f"{portfolio_id}-CASH-USD",
        },
        {
            "cash_account_id": "CASH-ACC-EUR-001",
            "portfolio_id": portfolio_id,
            "security_id": "CASH_EUR_BOOK_OPERATING",
            "display_name": "EUR Operating Cash",
            "account_currency": "EUR",
            "account_role": "OPERATING_CASH",
            "lifecycle_status": "ACTIVE",
            "opened_on": "2025-01-06",
            "source_system": "LOTUS_FRONT_OFFICE_SEED",
            "source_record_id": f"{portfolio_id}-CASH-EUR",
        },
    ]

    transactions = [
        _tx(
            "TXN-DEP-USD-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(1, 9),
            tx_type="DEPOSIT",
            quantity="900000",
            price="1",
            gross="900000",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            movement_direction="INFLOW",
            source_system="LOTUS_FRONT_OFFICE_SEED",
        ),
        _tx(
            "TXN-DEP-EUR-001",
            portfolio_id=portfolio_id,
            instrument_id="EUR-CASH",
            security_id="CASH_EUR_BOOK_OPERATING",
            when=tx_dt(2, 9),
            tx_type="DEPOSIT",
            quantity="335000",
            price="1",
            gross="335000",
            trade_currency="EUR",
            settlement_cash_account_id="CASH-ACC-EUR-001",
            movement_direction="INFLOW",
            transaction_fx_rate=fx_rate_for_transaction(tx_dt(2, 9), from_currency="EUR"),
            source_system="LOTUS_FRONT_OFFICE_SEED",
        ),
        _tx(
            "TXN-BUY-AAPL-001",
            portfolio_id=portfolio_id,
            instrument_id="AAPL",
            security_id="FO_EQ_AAPL_US",
            when=tx_dt(3),
            settlement_date=settle(3),
            tx_type="BUY",
            quantity="420",
            price="184.50",
            gross="77490.00",
            trade_currency="USD",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="BUY-AAPL-001"),
        ),
        _tx(
            "TXN-CASH-BUY-AAPL-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(3),
            settlement_date=settle(3),
            tx_type="SELL",
            quantity="77490.00",
            price="1",
            gross="77490.00",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="BUY-AAPL-001"),
        ),
        _tx(
            "TXN-BUY-MSFT-001",
            portfolio_id=portfolio_id,
            instrument_id="MSFT",
            security_id="FO_EQ_MSFT_US",
            when=tx_dt(12),
            settlement_date=settle(12),
            tx_type="BUY",
            quantity="260",
            price="401.25",
            gross="104325.00",
            trade_currency="USD",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="BUY-MSFT-001"),
        ),
        _tx(
            "TXN-CASH-BUY-MSFT-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(12),
            settlement_date=settle(12),
            tx_type="SELL",
            quantity="104325.00",
            price="1",
            gross="104325.00",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="BUY-MSFT-001"),
        ),
        _tx(
            "TXN-BUY-SAP-001",
            portfolio_id=portfolio_id,
            instrument_id="SAP",
            security_id="FO_EQ_SAP_DE",
            when=tx_dt(20),
            settlement_date=settle(20),
            tx_type="BUY",
            quantity="680",
            price="121.40",
            gross="82552.00",
            trade_currency="EUR",
            transaction_fx_rate=fx_rate_for_transaction(tx_dt(20), from_currency="EUR"),
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="BUY-SAP-001"),
        ),
        _tx(
            "TXN-CASH-BUY-SAP-001",
            portfolio_id=portfolio_id,
            instrument_id="EUR-CASH",
            security_id="CASH_EUR_BOOK_OPERATING",
            when=tx_dt(20),
            settlement_date=settle(20),
            tx_type="SELL",
            quantity="82552.00",
            price="1",
            gross="82552.00",
            trade_currency="EUR",
            settlement_cash_account_id="CASH-ACC-EUR-001",
            transaction_fx_rate=fx_rate_for_transaction(tx_dt(20), from_currency="EUR"),
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="BUY-SAP-001"),
        ),
        _tx(
            "TXN-BUY-WORLD-ETF-001",
            portfolio_id=portfolio_id,
            instrument_id="WORLD-ETF",
            security_id="FO_ETF_MSCI_WORLD",
            when=tx_dt(34),
            settlement_date=settle(34),
            tx_type="BUY",
            quantity="920",
            price="98.25",
            gross="90390.00",
            trade_currency="USD",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(
                portfolio_id=portfolio_id, event_code="BUY-WORLD-ETF-001"
            ),
        ),
        _tx(
            "TXN-CASH-BUY-WORLD-ETF-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(34),
            settlement_date=settle(34),
            tx_type="SELL",
            quantity="90390.00",
            price="1",
            gross="90390.00",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(
                portfolio_id=portfolio_id, event_code="BUY-WORLD-ETF-001"
            ),
        ),
        _tx(
            "TXN-BUY-BLK-ALLOC-001",
            portfolio_id=portfolio_id,
            instrument_id="BLK-GAF",
            security_id="FO_FUND_BLK_ALLOC",
            when=tx_dt(49),
            settlement_date=settle(49),
            tx_type="BUY",
            quantity="1480",
            price="107.25",
            gross="158730.00",
            trade_currency="EUR",
            transaction_fx_rate=fx_rate_for_transaction(tx_dt(49), from_currency="EUR"),
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(
                portfolio_id=portfolio_id, event_code="BUY-BLK-ALLOC-001"
            ),
        ),
        _tx(
            "TXN-CASH-BUY-BLK-ALLOC-001",
            portfolio_id=portfolio_id,
            instrument_id="EUR-CASH",
            security_id="CASH_EUR_BOOK_OPERATING",
            when=tx_dt(49),
            settlement_date=settle(49),
            tx_type="SELL",
            quantity="158730.00",
            price="1",
            gross="158730.00",
            trade_currency="EUR",
            settlement_cash_account_id="CASH-ACC-EUR-001",
            transaction_fx_rate=fx_rate_for_transaction(tx_dt(49), from_currency="EUR"),
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(
                portfolio_id=portfolio_id, event_code="BUY-BLK-ALLOC-001"
            ),
        ),
        _tx(
            "TXN-BUY-PIMCO-INC-001",
            portfolio_id=portfolio_id,
            instrument_id="PIMCO-INC",
            security_id="FO_FUND_PIMCO_INC",
            when=tx_dt(63),
            settlement_date=settle(63),
            tx_type="BUY",
            quantity="2400",
            price="101.80",
            gross="244320.00",
            trade_currency="USD",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(
                portfolio_id=portfolio_id, event_code="BUY-PIMCO-INC-001"
            ),
        ),
        _tx(
            "TXN-CASH-BUY-PIMCO-INC-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(63),
            settlement_date=settle(63),
            tx_type="SELL",
            quantity="244320.00",
            price="1",
            gross="244320.00",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(
                portfolio_id=portfolio_id, event_code="BUY-PIMCO-INC-001"
            ),
        ),
        _tx(
            "TXN-BUY-UST-001",
            portfolio_id=portfolio_id,
            instrument_id="UST-2030",
            security_id="FO_BOND_UST_2030",
            when=tx_dt(90),
            settlement_date=settle(90),
            tx_type="BUY",
            quantity="180",
            price="992.80",
            gross="178704.00",
            trade_currency="USD",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="BUY-UST-001"),
        ),
        _tx(
            "TXN-CASH-BUY-UST-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(90),
            settlement_date=settle(90),
            tx_type="SELL",
            quantity="178704.00",
            price="1",
            gross="178704.00",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="BUY-UST-001"),
        ),
        _tx(
            "TXN-BUY-SIEMENS-BOND-001",
            portfolio_id=portfolio_id,
            instrument_id="SIEMENS-2031",
            security_id="FO_BOND_SIEMENS_2031",
            when=tx_dt(118),
            settlement_date=settle(118),
            tx_type="BUY",
            quantity="75",
            price="985.50",
            gross="73912.50",
            trade_currency="EUR",
            transaction_fx_rate=fx_rate_for_transaction(tx_dt(118), from_currency="EUR"),
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(
                portfolio_id=portfolio_id, event_code="BUY-SIEMENS-BOND-001"
            ),
        ),
        _tx(
            "TXN-CASH-BUY-SIEMENS-BOND-001",
            portfolio_id=portfolio_id,
            instrument_id="EUR-CASH",
            security_id="CASH_EUR_BOOK_OPERATING",
            when=tx_dt(118),
            settlement_date=settle(118),
            tx_type="SELL",
            quantity="73912.50",
            price="1",
            gross="73912.50",
            trade_currency="EUR",
            settlement_cash_account_id="CASH-ACC-EUR-001",
            transaction_fx_rate=fx_rate_for_transaction(tx_dt(118), from_currency="EUR"),
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(
                portfolio_id=portfolio_id, event_code="BUY-SIEMENS-BOND-001"
            ),
        ),
        _tx(
            "TXN-BUY-PRIVCREDIT-001",
            portfolio_id=portfolio_id,
            instrument_id="PRIVCREDIT-A",
            security_id="FO_PRIV_PRIVATE_CREDIT_A",
            when=tx_dt(146),
            settlement_date=settle(146, 5),
            tx_type="BUY",
            quantity="1250",
            price="100.00",
            gross="125000.00",
            trade_currency="USD",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(
                portfolio_id=portfolio_id, event_code="BUY-PRIVCREDIT-001"
            ),
        ),
        _tx(
            "TXN-CASH-BUY-PRIVCREDIT-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(146),
            settlement_date=settle(146, 5),
            tx_type="SELL",
            quantity="125000.00",
            price="1",
            gross="125000.00",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(
                portfolio_id=portfolio_id, event_code="BUY-PRIVCREDIT-001"
            ),
        ),
        _tx(
            "TXN-DIV-AAPL-001",
            portfolio_id=portfolio_id,
            instrument_id="AAPL",
            security_id="FO_EQ_AAPL_US",
            when=tx_dt(337),
            settlement_date=settle(337, 0),
            tx_type="DIVIDEND",
            quantity="0",
            price="0",
            gross="850.00",
            trade_currency="USD",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="DIV-AAPL-001"),
        ),
        _tx(
            "TXN-CASH-DIV-AAPL-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(337),
            settlement_date=settle(337, 0),
            tx_type="BUY",
            quantity="850.00",
            price="1",
            gross="850.00",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="DIV-AAPL-001"),
        ),
        _tx(
            "TXN-INT-UST-001",
            portfolio_id=portfolio_id,
            instrument_id="UST-2030",
            security_id="FO_BOND_UST_2030",
            when=tx_dt(345),
            settlement_date=settle(345, 0),
            tx_type="INTEREST",
            quantity="0",
            price="0",
            gross="1280.75",
            trade_currency="USD",
            interest_direction="INCOME",
            withholding_tax_amount="81.75",
            other_interest_deductions_amount="12.00",
            net_interest_amount="1187.00",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="INT-UST-001"),
        ),
        _tx(
            "TXN-CASH-INT-UST-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(345),
            settlement_date=settle(345, 0),
            tx_type="BUY",
            quantity="1187.00",
            price="1",
            gross="1187.00",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="INT-UST-001"),
        ),
        _tx(
            "TXN-DEP-USD-TOPUP-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(339, 9),
            tx_type="DEPOSIT",
            quantity="40000",
            price="1",
            gross="40000",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            movement_direction="INFLOW",
            source_system="LOTUS_FRONT_OFFICE_SEED",
        ),
        _cash_tx(
            "TXN-FEE-ADVISORY-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(346),
            settlement_date=settle(346, 0),
            tx_type="FEE",
            gross="275.00",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            movement_direction="OUTFLOW",
            source_system="LOTUS_FRONT_OFFICE_SEED",
        ),
        _tx(
            "TXN-SELL-AAPL-001",
            portfolio_id=portfolio_id,
            instrument_id="AAPL",
            security_id="FO_EQ_AAPL_US",
            when=tx_dt(334),
            settlement_date=settle(334),
            tx_type="SELL",
            quantity="110",
            price="207.40",
            gross="22814.00",
            trade_currency="USD",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="SELL-AAPL-001"),
        ),
        _tx(
            "TXN-CASH-SELL-AAPL-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(334),
            settlement_date=settle(334),
            tx_type="BUY",
            quantity="22814.00",
            price="1",
            gross="22814.00",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            source_system="LOTUS_FRONT_OFFICE_SEED",
            **_paired_internal_leg_metadata(portfolio_id=portfolio_id, event_code="SELL-AAPL-001"),
        ),
        _tx(
            "TXN-WITHDRAWAL-PLANNED-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(360),
            settlement_date=settle(360, 4),
            tx_type="WITHDRAWAL",
            quantity="25000",
            price="1",
            gross="25000",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            movement_direction="OUTFLOW",
            source_system="LOTUS_FRONT_OFFICE_SEED",
        ),
        _tx(
            "TXN-WITHDRAWAL-FUTURE-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=date_dt(forward_withdrawal_date),
            settlement_date=date_dt(forward_withdrawal_settlement_date, 16),
            tx_type="WITHDRAWAL",
            quantity="18000",
            price="1",
            gross="18000",
            trade_currency="USD",
            settlement_cash_account_id="CASH-ACC-USD-001",
            movement_direction="OUTFLOW",
            source_system="LOTUS_FRONT_OFFICE_SEED",
        ),
    ]

    _validate_front_office_cash_transactions(transactions)
    _validate_front_office_internal_transaction_pairs(transactions)

    benchmark_reference = _build_benchmark_reference_data(
        dates=fx_calendar_dates,
        start_date=effective_benchmark_start,
    )
    benchmark_reference["benchmark_definitions"] = [
        {
            **definition,
            "benchmark_id": benchmark_id,
            "benchmark_name": "Private Banking Global Balanced 60/40",
            "benchmark_provider": "LOTUS_FRONT_OFFICE_SEED",
            "source_vendor": "LOTUS_FRONT_OFFICE_SEED",
            "source_record_id": f"{benchmark_id.lower()}_definition",
        }
        for definition in benchmark_reference["benchmark_definitions"]
    ]
    benchmark_reference["benchmark_compositions"] = [
        {
            **composition,
            "benchmark_id": benchmark_id,
            "source_vendor": "LOTUS_FRONT_OFFICE_SEED",
            "source_record_id": composition["source_record_id"].replace(
                DEFAULT_DEMO_BENCHMARK_ID.lower(),
                benchmark_id.lower(),
            ),
            "rebalance_event_id": composition["rebalance_event_id"].replace(
                DEFAULT_DEMO_BENCHMARK_ID.lower(),
                benchmark_id.lower(),
            ),
        }
        for composition in benchmark_reference["benchmark_compositions"]
    ]
    benchmark_reference["benchmark_return_series"] = [
        {
            **series_row,
            "series_id": series_row["series_id"].replace(
                DEFAULT_DEMO_BENCHMARK_ID.lower(),
                benchmark_id.lower(),
            ),
            "benchmark_id": benchmark_id,
            "source_vendor": "LOTUS_FRONT_OFFICE_SEED",
            "source_record_id": series_row["source_record_id"].replace(
                DEFAULT_DEMO_BENCHMARK_ID.lower(),
                benchmark_id.lower(),
            ),
        }
        for series_row in benchmark_reference["benchmark_return_series"]
    ]
    benchmark_reference["benchmark_assignments"] = [
        {
            **assignment,
            "portfolio_id": portfolio_id,
            "benchmark_id": benchmark_id,
            "effective_from": effective_benchmark_start.isoformat(),
            "assignment_source": "front_office_portfolio_seed",
            "source_system": "LOTUS_FRONT_OFFICE_SEED",
        }
        for assignment in benchmark_reference["benchmark_assignments"]
    ]
    risk_free_reference = build_risk_free_reference_data(
        start_date=start_date,
        end_date=end_date + timedelta(days=30),
        currency="USD",
        source_vendor="LOTUS_FRONT_OFFICE_SEED",
        source_prefix="front_office_risk_free",
    )

    market_price_specs = {
        "FO_EQ_AAPL_US": (Decimal("184.00"), Decimal("212.00")),
        "FO_EQ_MSFT_US": (Decimal("398.00"), Decimal("428.00")),
        "FO_EQ_SAP_DE": (Decimal("118.50"), Decimal("129.20")),
        "FO_ETF_MSCI_WORLD": (Decimal("97.00"), Decimal("103.80")),
        "FO_FUND_BLK_ALLOC": (Decimal("104.20"), Decimal("108.40")),
        "FO_FUND_PIMCO_INC": (Decimal("100.10"), Decimal("102.40")),
        "FO_BOND_UST_2030": (Decimal("98.30"), Decimal("101.35")),
        "FO_BOND_SIEMENS_2031": (Decimal("97.90"), Decimal("99.25")),
        "FO_PRIV_PRIVATE_CREDIT_A": (Decimal("99.20"), Decimal("101.10")),
    }

    market_prices: list[dict[str, Any]] = []
    for current_date in calendar_dates:
        market_prices.extend(
            [
                {
                    "security_id": "CASH_USD_BOOK_OPERATING",
                    "price_date": current_date,
                    "price": "1.0000000000",
                    "currency": "USD",
                },
                {
                    "security_id": "CASH_EUR_BOOK_OPERATING",
                    "price_date": current_date,
                    "price": "1.0000000000",
                    "currency": "EUR",
                },
            ]
        )

    for security_id, (start_price, end_price) in market_price_specs.items():
        security_dates = calendar_dates
        for current_date, price in zip(
            security_dates,
            _interpolate_prices(dates=security_dates, start_price=start_price, end_price=end_price),
            strict=True,
        ):
            currency = next(
                instrument["currency"]
                for instrument in instruments
                if instrument["security_id"] == security_id
            )
            market_prices.append(
                {
                    "security_id": security_id,
                    "price_date": current_date,
                    "price": price,
                    "currency": currency,
                }
            )

    fx_rates: list[dict[str, Any]] = []
    for current_date, eur_usd_rate in zip(fx_calendar_dates, eur_usd, strict=True):
        inverse_rate = _invert_rate(eur_usd_rate)
        fx_rates.extend(
            [
                {
                    "from_currency": "EUR",
                    "to_currency": "USD",
                    "rate_date": current_date,
                    "rate": eur_usd_rate,
                },
                {
                    "from_currency": "USD",
                    "to_currency": "EUR",
                    "rate_date": current_date,
                    "rate": inverse_rate,
                },
            ]
        )

    return {
        "source_system": "LOTUS_FRONT_OFFICE_SEED",
        "mode": "UPSERT",
        "business_dates": [{"business_date": current_date} for current_date in business_dates],
        "portfolios": portfolios,
        "instruments": instruments,
        "cash_accounts": cash_accounts,
        "transactions": transactions,
        "market_prices": market_prices,
        "fx_rates": fx_rates,
        "as_of_date": as_of_date,
        **benchmark_reference,
        **risk_free_reference,
    }


def _portfolio_exists(query_base_url: str, portfolio_id: str) -> bool:
    _, payload = _request_json("GET", f"{query_base_url}/portfolios?portfolio_id={portfolio_id}")
    return any(item.get("portfolio_id") == portfolio_id for item in payload.get("portfolios") or [])


def _wait_for_portfolio_persistence(
    *,
    query_base_url: str,
    portfolio_id: str,
    wait_seconds: int,
    poll_interval_seconds: int,
) -> None:
    deadline = datetime.now(tz=UTC) + timedelta(seconds=wait_seconds)
    while datetime.now(tz=UTC) <= deadline:
        if _portfolio_exists(query_base_url, portfolio_id):
            return
        LOGGER.info(
            "Waiting for portfolio %s to persist before ingesting dependent reference data.",
            portfolio_id,
        )
        time.sleep(poll_interval_seconds)
    raise TimeoutError(
        f"Portfolio {portfolio_id} was not visible in query service within {wait_seconds} seconds."
    )


def _ingest_reference_data(ingestion_base_url: str, bundle: dict[str, Any]) -> None:
    reference_payloads = (
        ("/ingest/reference/cash-accounts", {"cash_accounts": bundle["cash_accounts"]}),
        ("/ingest/indices", {"indices": bundle["indices"]}),
        ("/ingest/index-price-series", {"index_price_series": bundle["index_price_series"]}),
        ("/ingest/index-return-series", {"index_return_series": bundle["index_return_series"]}),
        (
            "/ingest/benchmark-definitions",
            {"benchmark_definitions": bundle["benchmark_definitions"]},
        ),
        (
            "/ingest/benchmark-compositions",
            {"benchmark_compositions": bundle["benchmark_compositions"]},
        ),
        (
            "/ingest/benchmark-return-series",
            {"benchmark_return_series": bundle["benchmark_return_series"]},
        ),
        (
            "/ingest/benchmark-assignments",
            {"benchmark_assignments": bundle["benchmark_assignments"]},
        ),
        ("/ingest/risk-free-series", {"risk_free_series": bundle["risk_free_series"]}),
    )
    for endpoint, payload in reference_payloads:
        _request_json("POST", f"{ingestion_base_url}{endpoint}", payload=payload)


def _ingest_front_office_core_data(
    *,
    ingestion_base_url: str,
    query_base_url: str,
    bundle: dict[str, Any],
    portfolio_id: str,
    wait_seconds: int,
    poll_interval_seconds: int,
) -> None:
    core_payloads = (
        ("/ingest/business-dates", {"business_dates": bundle["business_dates"]}),
        ("/ingest/portfolios", {"portfolios": bundle["portfolios"]}),
        ("/ingest/instruments", {"instruments": bundle["instruments"]}),
        ("/ingest/fx-rates", {"fx_rates": bundle["fx_rates"]}),
        ("/ingest/market-prices", {"market_prices": bundle["market_prices"]}),
        ("/ingest/transactions", {"transactions": bundle["transactions"]}),
    )

    for endpoint, payload in core_payloads:
        _request_json("POST", f"{ingestion_base_url}{endpoint}", payload=payload)
        if endpoint == "/ingest/portfolios":
            _wait_for_portfolio_persistence(
                query_base_url=query_base_url,
                portfolio_id=portfolio_id,
                wait_seconds=wait_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )


def _reprocess_front_office_transactions(ingestion_base_url: str, bundle: dict[str, Any]) -> None:
    transaction_ids = [
        transaction["transaction_id"]
        for transaction in bundle["transactions"]
        if isinstance(transaction.get("transaction_id"), str)
    ]
    if not transaction_ids:
        return
    _request_json(
        "POST",
        f"{ingestion_base_url}/reprocess/transactions",
        payload={"transaction_ids": transaction_ids},
    )


def _date_at_or_after(actual: str | None, expected: str) -> bool:
    if not actual:
        return False
    return date.fromisoformat(actual) >= date.fromisoformat(expected)


def _front_office_analytics_are_fresh(
    *,
    analytics_reference: dict[str, Any],
    performance_summary: dict[str, Any],
    expected_end_date: str,
) -> bool:
    return_path = (performance_summary.get("capabilities") or {}).get("return_path") or {}
    return (
        _date_at_or_after(analytics_reference.get("performance_end_date"), expected_end_date)
        and _date_at_or_after(performance_summary.get("report_end_date"), expected_end_date)
        and _date_at_or_after(return_path.get("latest_available_date"), expected_end_date)
    )


def _extract_readiness_summary(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    blocking_reasons = readiness_payload.get("blocking_reasons") or []
    return {
        "resolved_as_of_date": readiness_payload.get("resolved_as_of_date"),
        "holdings_status": (readiness_payload.get("holdings") or {}).get("status"),
        "pricing_status": (readiness_payload.get("pricing") or {}).get("status"),
        "transactions_status": (readiness_payload.get("transactions") or {}).get("status"),
        "reporting_status": (readiness_payload.get("reporting") or {}).get("status"),
        "blocking_reason_codes": [
            reason.get("code")
            for reason in blocking_reasons
            if isinstance(reason, dict) and reason.get("code")
        ],
        "latest_booked_transaction_date": readiness_payload.get("latest_booked_transaction_date"),
        "latest_booked_position_snapshot_date": readiness_payload.get(
            "latest_booked_position_snapshot_date"
        ),
        "snapshot_valuation_total_positions": readiness_payload.get(
            "snapshot_valuation_total_positions"
        ),
        "snapshot_valuation_valued_positions": readiness_payload.get(
            "snapshot_valuation_valued_positions"
        ),
        "snapshot_valuation_unvalued_positions": readiness_payload.get(
            "snapshot_valuation_unvalued_positions"
        ),
        "missing_historical_fx_dependencies": (
            (readiness_payload.get("missing_historical_fx_dependencies") or {}).get("missing_count")
        ),
    }


def _extract_support_overview_summary(overview_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "pending_aggregation_jobs": overview_payload.get("pending_aggregation_jobs"),
        "processing_aggregation_jobs": overview_payload.get("processing_aggregation_jobs"),
        "stale_processing_aggregation_jobs": overview_payload.get(
            "stale_processing_aggregation_jobs"
        ),
        "failed_aggregation_jobs": overview_payload.get("failed_aggregation_jobs"),
        "oldest_pending_aggregation_date": overview_payload.get("oldest_pending_aggregation_date"),
        "latest_booked_transaction_date": overview_payload.get("latest_booked_transaction_date"),
        "latest_booked_position_snapshot_date": overview_payload.get(
            "latest_booked_position_snapshot_date"
        ),
    }


def _collect_front_office_readiness_diagnostics(
    *,
    query_control_plane_base_url: str,
    portfolio_id: str,
    as_of_date: str,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}

    try:
        _, readiness_payload = _request_json(
            "GET",
            f"{query_control_plane_base_url}/support/portfolios/{portfolio_id}/readiness"
            f"?as_of_date={as_of_date}",
        )
        diagnostics["readiness"] = _extract_readiness_summary(readiness_payload)
    except RuntimeError as exc:
        diagnostics["readiness_error"] = str(exc)

    try:
        _, overview_payload = _request_json(
            "GET",
            f"{query_control_plane_base_url}/support/portfolios/{portfolio_id}/overview",
        )
        diagnostics["support_overview"] = _extract_support_overview_summary(overview_payload)
    except RuntimeError as exc:
        diagnostics["support_overview_error"] = str(exc)

    try:
        _, aggregation_jobs_payload = _request_json(
            "GET",
            f"{query_control_plane_base_url}/support/portfolios/{portfolio_id}/aggregation-jobs"
            f"?business_date={as_of_date}&limit=5",
        )
        diagnostics["aggregation_jobs"] = {
            "total": aggregation_jobs_payload.get("total"),
            "job_ids": [
                row.get("job_id")
                for row in aggregation_jobs_payload.get("items") or []
                if isinstance(row, dict) and row.get("job_id") is not None
            ],
            "statuses": [
                row.get("status")
                for row in aggregation_jobs_payload.get("items") or []
                if isinstance(row, dict) and row.get("status")
            ],
        }
    except RuntimeError as exc:
        diagnostics["aggregation_jobs_error"] = str(exc)

    return diagnostics


def _cleanup_existing_front_office_seed(
    *,
    postgres_container: str,
    portfolio_id: str,
    benchmark_id: str,
) -> None:
    sql = build_front_office_seed_cleanup_sql(
        portfolio_id=portfolio_id,
        benchmark_id=benchmark_id,
    )
    subprocess.run(
        [
            "docker",
            "exec",
            postgres_container,
            "psql",
            "-U",
            "user",
            "-d",
            "portfolio_db",
            "-c",
            sql,
        ],
        check=True,
    )


def _verify_front_office_portfolio(
    *,
    query_base_url: str,
    query_control_plane_base_url: str,
    gateway_base_url: str,
    expected: FrontOfficePortfolioExpectation,
    as_of_date: str,
    end_date: str,
    wait_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, Any]:
    deadline = datetime.now(tz=UTC) + timedelta(seconds=wait_seconds)
    last_observation: dict[str, Any] | None = None
    while datetime.now(tz=UTC) < deadline:
        try:
            _, positions_payload = _request_json(
                "GET",
                f"{query_base_url}/portfolios/{expected.portfolio_id}/positions"
                f"?as_of_date={as_of_date}",
            )
            _, transactions_payload = _request_json(
                "GET",
                f"{query_base_url}/portfolios/{expected.portfolio_id}/transactions"
                "?limit=300&include_projected=true",
            )
            _, allocation_payload = _request_json(
                "POST",
                f"{query_base_url}/reporting/asset-allocation/query",
                payload={
                    "scope": {"portfolio_id": expected.portfolio_id},
                    "as_of_date": as_of_date,
                    "reporting_currency": "USD",
                    "dimensions": ["asset_class", "sector", "region", "currency"],
                },
            )
            _, cash_payload = _request_json(
                "GET",
                f"{query_base_url}/portfolios/{expected.portfolio_id}/cash-balances"
                f"?as_of_date={as_of_date}&reporting_currency=USD",
            )
            _, benchmark_assignment = _request_json(
                "POST",
                f"{query_control_plane_base_url}/integration/portfolios/{expected.portfolio_id}/benchmark-assignment",
                payload={"as_of_date": as_of_date, "consumer_system": "lotus-performance"},
            )
            _, analytics_reference = _request_json(
                "POST",
                f"{query_control_plane_base_url}/integration/portfolios/{expected.portfolio_id}/analytics/reference",
                payload={"as_of_date": as_of_date, "consumer_system": "lotus-performance"},
            )
            _, support_overview = _request_json(
                "GET",
                f"{query_control_plane_base_url}/support/portfolios/{expected.portfolio_id}/overview",
            )
            _, cashflow_projection = _request_json(
                "GET",
                f"{query_base_url}/portfolios/{expected.portfolio_id}/cashflow-projection"
                f"?as_of_date={as_of_date}&horizon_days=30&include_projected=true",
            )
            _, performance_summary = _request_json(
                "GET",
                f"{gateway_base_url}/api/v1/workbench/{expected.portfolio_id}/performance/summary"
                f"?period=YTD&chart_frequency=monthly&contribution_dimension=asset_class"
                f"&attribution_dimension=asset_class&detail_basis=NET",
            )
        except RuntimeError:
            LOGGER.info("Verification still waiting on downstream services.")
            continue

        positions = positions_payload.get("positions") or []
        valued = [
            row
            for row in positions
            if isinstance(row.get("valuation"), dict)
            and row["valuation"].get("market_value") is not None
        ]
        cash_accounts = cash_payload.get("cash_accounts") or []
        allocation_views = allocation_payload.get("views") or []
        total_transactions = int(transactions_payload.get("total", 0))
        transaction_rows = transactions_payload.get("transactions") or []
        income_rows, activity_rows = _derive_reporting_summary_signals(
            transactions=transaction_rows,
            start_date="2026-02-27",
            end_date=end_date,
        )
        projected_cashflow_points = cashflow_projection.get("points") or []
        has_non_zero_projection = any(
            str(point.get("net_cashflow")) not in {"0", "0.0", "0.00", "0.0000", "0E-10"}
            for point in projected_cashflow_points
            if isinstance(point, dict)
        )
        last_observation = {
            "positions": len(positions),
            "valued_positions": len(valued),
            "transactions": total_transactions,
            "cash_accounts": len(cash_accounts),
            "allocation_views": len(allocation_views),
            "income_types": len(income_rows),
            "activity_buckets": len(activity_rows),
            "projected_cashflow_points": len(projected_cashflow_points),
            "has_non_zero_projection": has_non_zero_projection,
            "positions_data_quality_status": positions_payload.get("data_quality_status"),
            "cash_data_quality_status": cash_payload.get("data_quality_status"),
            "pending_valuation_jobs": support_overview.get("pending_valuation_jobs"),
            "processing_valuation_jobs": support_overview.get("processing_valuation_jobs"),
            "pending_aggregation_jobs": support_overview.get("pending_aggregation_jobs"),
            "processing_aggregation_jobs": support_overview.get("processing_aggregation_jobs"),
            "benchmark_code": performance_summary.get("benchmark_code"),
            "analytics_performance_end_date": analytics_reference.get("performance_end_date"),
            "performance_report_end_date": performance_summary.get("report_end_date"),
            "return_path_latest_available_date": (
                performance_summary.get("capabilities", {})
                .get("return_path", {})
                .get("latest_available_date")
            ),
        }

        if (
            len(positions) >= expected.min_positions
            and len(valued) >= expected.min_valued_positions
            and total_transactions >= expected.min_transactions
            and len(cash_accounts) >= expected.min_cash_accounts
            and len(allocation_views) >= expected.min_allocation_views
            and income_rows
            and activity_rows
            and len(projected_cashflow_points) >= expected.min_projected_cashflow_points
            and has_non_zero_projection
            and positions_payload.get("data_quality_status") == "COMPLETE"
            and cash_payload.get("data_quality_status") == "COMPLETE"
            and int(support_overview.get("pending_valuation_jobs") or 0) == 0
            and int(support_overview.get("processing_valuation_jobs") or 0) == 0
            and int(support_overview.get("pending_aggregation_jobs") or 0) == 0
            and int(support_overview.get("processing_aggregation_jobs") or 0) == 0
            and benchmark_assignment.get("benchmark_id")
            and performance_summary.get("benchmark_code")
            and _front_office_analytics_are_fresh(
                analytics_reference=analytics_reference,
                performance_summary=performance_summary,
                expected_end_date=end_date,
            )
        ):
            return {
                "portfolio_id": expected.portfolio_id,
                "positions": len(positions),
                "valued_positions": len(valued),
                "transactions": total_transactions,
                "cash_accounts": len(cash_accounts),
                "allocation_views": len(allocation_views),
                "income_types": len(income_rows),
                "activity_buckets": len(activity_rows),
                "projected_cashflow_points": len(projected_cashflow_points),
                "pending_valuation_jobs": support_overview.get("pending_valuation_jobs"),
                "processing_valuation_jobs": support_overview.get("processing_valuation_jobs"),
                "pending_aggregation_jobs": support_overview.get("pending_aggregation_jobs"),
                "processing_aggregation_jobs": support_overview.get("processing_aggregation_jobs"),
                "positions_data_quality_status": positions_payload.get("data_quality_status"),
                "cash_data_quality_status": cash_payload.get("data_quality_status"),
                "benchmark_code": performance_summary.get("benchmark_code"),
                "analytics_performance_end_date": analytics_reference.get("performance_end_date"),
                "performance_report_end_date": performance_summary.get("report_end_date"),
                "return_path_latest_available_date": (
                    performance_summary.get("capabilities", {})
                    .get("return_path", {})
                    .get("latest_available_date")
                ),
            }

        LOGGER.info(
            "Front-office verification waiting on readiness for %s: %s",
            expected.portfolio_id,
            last_observation,
        )

    readiness_diagnostics = _collect_front_office_readiness_diagnostics(
        query_control_plane_base_url=query_control_plane_base_url,
        portfolio_id=expected.portfolio_id,
        as_of_date=as_of_date,
    )
    raise TimeoutError(
        "Timed out verifying front-office portfolio seed for "
        f"{expected.portfolio_id}. "
        f"Last observation: {last_observation}. "
        f"Readiness diagnostics: {readiness_diagnostics}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a realistic front-office portfolio scenario."
    )
    parser.add_argument("--portfolio-id", default=FRONT_OFFICE_SEED_CONTRACT.portfolio_id)
    parser.add_argument("--start-date", default=FRONT_OFFICE_SEED_CONTRACT.seed_start_date)
    parser.add_argument("--end-date", default=FRONT_OFFICE_SEED_CONTRACT.canonical_as_of_date)
    parser.add_argument(
        "--benchmark-start-date",
        default=FRONT_OFFICE_SEED_CONTRACT.benchmark_start_date,
    )
    parser.add_argument("--benchmark-id", default=FRONT_OFFICE_SEED_CONTRACT.benchmark_id)
    parser.add_argument("--ingestion-base-url", default="http://127.0.0.1:8200")
    parser.add_argument("--query-base-url", default="http://127.0.0.1:8201")
    parser.add_argument("--query-control-plane-base-url", default="http://127.0.0.1:8202")
    parser.add_argument("--gateway-base-url", default="http://gateway.dev.lotus")
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--poll-interval-seconds", type=int, default=3)
    parser.add_argument("--postgres-container", default=DEFAULT_POSTGRES_CONTAINER)
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--ingest-only", action="store_true")
    parser.add_argument("--force-ingest", action="store_true")
    parser.add_argument(
        "--skip-reprocess",
        action="store_true",
        help="Do not queue transaction reprocessing after bundle ingest.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    if args.verify_only and args.ingest_only:
        raise ValueError("Cannot use --verify-only with --ingest-only")

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    benchmark_start_date = date.fromisoformat(args.benchmark_start_date)

    ingestion_base_url = args.ingestion_base_url.rstrip("/")
    query_base_url = args.query_base_url.rstrip("/")
    query_control_plane_base_url = args.query_control_plane_base_url.rstrip("/")
    gateway_base_url = args.gateway_base_url.rstrip("/")

    _wait_ready(f"{ingestion_base_url}/health/ready", args.wait_seconds, args.poll_interval_seconds)
    _wait_ready(f"{query_base_url}/health/ready", args.wait_seconds, args.poll_interval_seconds)
    _wait_ready(
        f"{query_control_plane_base_url}/health/ready",
        args.wait_seconds,
        args.poll_interval_seconds,
    )

    bundle = build_front_office_portfolio_bundle(
        portfolio_id=args.portfolio_id,
        start_date=start_date,
        end_date=end_date,
        benchmark_start_date=benchmark_start_date,
        benchmark_id=args.benchmark_id,
    )
    if not args.verify_only:
        if not args.skip_cleanup:
            _cleanup_existing_front_office_seed(
                postgres_container=args.postgres_container,
                portfolio_id=args.portfolio_id,
                benchmark_id=args.benchmark_id,
            )
        should_ingest = args.force_ingest or not args.skip_cleanup
        if not should_ingest:
            should_ingest = not _portfolio_exists(query_base_url, args.portfolio_id)
        if should_ingest:
            _ingest_front_office_core_data(
                ingestion_base_url=ingestion_base_url,
                query_base_url=query_base_url,
                bundle=bundle,
                portfolio_id=args.portfolio_id,
                wait_seconds=args.wait_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
        _ingest_reference_data(ingestion_base_url, bundle)
        if should_ingest and not args.skip_reprocess:
            _reprocess_front_office_transactions(ingestion_base_url, bundle)

    if not args.ingest_only:
        verification = _verify_front_office_portfolio(
            query_base_url=query_base_url,
            query_control_plane_base_url=query_control_plane_base_url,
            gateway_base_url=gateway_base_url,
            expected=FRONT_OFFICE_EXPECTATION,
            as_of_date=end_date.isoformat(),
            end_date=end_date.isoformat(),
            wait_seconds=args.wait_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
        LOGGER.info("Front-office seed verified: %s", verification)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
