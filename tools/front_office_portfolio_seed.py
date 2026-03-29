from __future__ import annotations

import argparse
import logging
import subprocess
import sys
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
)

LOGGER = logging.getLogger("front_office_portfolio_seed")

DEFAULT_PORTFOLIO_ID = "PB_SG_GLOBAL_BAL_001"
DEFAULT_BENCHMARK_ID = "BMK_PB_GLOBAL_BALANCED_60_40"
DEFAULT_POSTGRES_CONTAINER = "lotus-core-app-local-postgres-1"


@dataclass(frozen=True)
class FrontOfficePortfolioExpectation:
    portfolio_id: str
    min_positions: int
    min_valued_positions: int
    min_transactions: int
    min_cash_accounts: int


FRONT_OFFICE_EXPECTATION = FrontOfficePortfolioExpectation(
    portfolio_id=DEFAULT_PORTFOLIO_ID,
    min_positions=10,
    min_valued_positions=10,
    min_transactions=26,
    min_cash_accounts=2,
)


def build_front_office_seed_cleanup_sql(*, portfolio_id: str, benchmark_id: str) -> str:
    return "\n".join(
        [
            (
                "delete from portfolio_benchmark_assignments "
                f"where portfolio_id = '{portfolio_id}' and benchmark_id = '{benchmark_id}';"
            ),
            f"delete from benchmark_composition_series where benchmark_id = '{benchmark_id}';",
            f"delete from benchmark_return_series where benchmark_id = '{benchmark_id}';",
            f"delete from benchmark_definitions where benchmark_id = '{benchmark_id}';",
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
            source_system="LOTUS_FRONT_OFFICE_SEED",
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
            source_system="LOTUS_FRONT_OFFICE_SEED",
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
            source_system="LOTUS_FRONT_OFFICE_SEED",
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
            source_system="LOTUS_FRONT_OFFICE_SEED",
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
            source_system="LOTUS_FRONT_OFFICE_SEED",
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
            source_system="LOTUS_FRONT_OFFICE_SEED",
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
        _tx(
            "TXN-FEE-ADVISORY-001",
            portfolio_id=portfolio_id,
            instrument_id="USD-CASH",
            security_id="CASH_USD_BOOK_OPERATING",
            when=tx_dt(346),
            settlement_date=settle(346, 0),
            tx_type="FEE",
            quantity="1",
            price="275.00",
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
            when=tx_dt(372),
            settlement_date=settle(372, 3),
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

    eur_usd = _interpolate_prices(
        dates=fx_calendar_dates,
        start_price=Decimal("1.072500"),
        end_price=Decimal("1.110000"),
        precision="0.000001",
    )
    fx_rates: list[dict[str, Any]] = []
    for current_date, eur_usd_rate in zip(fx_calendar_dates, eur_usd, strict=True):
        inverse_rate = format(
            (Decimal("1") / Decimal(eur_usd_rate)).quantize(Decimal("0.000001")),
            "f",
        )
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
    }


def _build_portfolio_bundle_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_system": bundle["source_system"],
        "mode": bundle["mode"],
        "business_dates": bundle["business_dates"],
        "portfolios": bundle["portfolios"],
        "instruments": bundle["instruments"],
        "transactions": bundle["transactions"],
        "market_prices": bundle["market_prices"],
        "fx_rates": bundle["fx_rates"],
        "as_of_date": bundle["as_of_date"],
    }


def _portfolio_exists(query_base_url: str, portfolio_id: str) -> bool:
    _, payload = _request_json("GET", f"{query_base_url}/portfolios?portfolio_id={portfolio_id}")
    return any(item.get("portfolio_id") == portfolio_id for item in payload.get("portfolios") or [])


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
    )
    for endpoint, payload in reference_payloads:
        _request_json("POST", f"{ingestion_base_url}{endpoint}", payload=payload)


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
    while datetime.now(tz=UTC) < deadline:
        try:
            _, positions_payload = _request_json(
                "GET", f"{query_base_url}/portfolios/{expected.portfolio_id}/positions"
            )
            _, transactions_payload = _request_json(
                "GET", f"{query_base_url}/portfolios/{expected.portfolio_id}/transactions?limit=300"
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
                "POST",
                f"{query_base_url}/reporting/cash-balances/query",
                payload={
                    "portfolio_id": expected.portfolio_id,
                    "as_of_date": as_of_date,
                    "reporting_currency": "USD",
                },
            )
            _, income_payload = _request_json(
                "POST",
                f"{query_base_url}/reporting/income-summary/query",
                payload={
                    "scope": {"portfolio_id": expected.portfolio_id},
                    "window": {"start_date": "2026-02-27", "end_date": end_date},
                    "reporting_currency": "USD",
                },
            )
            _, activity_payload = _request_json(
                "POST",
                f"{query_base_url}/reporting/activity-summary/query",
                payload={
                    "scope": {"portfolio_id": expected.portfolio_id},
                    "window": {"start_date": "2026-02-27", "end_date": end_date},
                    "reporting_currency": "USD",
                },
            )
            _, benchmark_assignment = _request_json(
                "POST",
                f"{query_control_plane_base_url}/integration/portfolios/{expected.portfolio_id}/benchmark-assignment",
                payload={"as_of_date": as_of_date, "consumer_system": "lotus-performance"},
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
        income_rows = ((income_payload.get("portfolios") or [{}])[0]).get("income_types") or []
        activity_rows = ((activity_payload.get("portfolios") or [{}])[0]).get("buckets") or []
        allocation_views = allocation_payload.get("views") or []
        total_transactions = int(transactions_payload.get("total", 0))
        projected_cashflow_points = cashflow_projection.get("points") or []
        has_non_zero_projection = any(
            str(point.get("net_cashflow")) not in {"0", "0.0", "0.00", "0.0000", "0E-10"}
            for point in projected_cashflow_points
            if isinstance(point, dict)
        )

        if (
            len(positions) >= expected.min_positions
            and len(valued) >= expected.min_valued_positions
            and total_transactions >= expected.min_transactions
            and len(cash_accounts) >= expected.min_cash_accounts
            and allocation_views
            and income_rows
            and activity_rows
            and has_non_zero_projection
            and benchmark_assignment.get("benchmark_id")
            and performance_summary.get("benchmark_code")
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
                "benchmark_code": performance_summary.get("benchmark_code"),
            }

    raise TimeoutError(
        f"Timed out verifying front-office portfolio seed for {expected.portfolio_id}."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a realistic front-office portfolio scenario."
    )
    parser.add_argument("--portfolio-id", default=DEFAULT_PORTFOLIO_ID)
    parser.add_argument("--start-date", default="2025-03-31")
    parser.add_argument("--end-date", default="2026-03-28")
    parser.add_argument("--benchmark-start-date", default="2025-01-06")
    parser.add_argument("--benchmark-id", default=DEFAULT_BENCHMARK_ID)
    parser.add_argument("--ingestion-base-url", default="http://127.0.0.1:8200")
    parser.add_argument("--query-base-url", default="http://127.0.0.1:8201")
    parser.add_argument("--query-control-plane-base-url", default="http://127.0.0.1:8202")
    parser.add_argument("--gateway-base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--poll-interval-seconds", type=int, default=3)
    parser.add_argument("--postgres-container", default=DEFAULT_POSTGRES_CONTAINER)
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--ingest-only", action="store_true")
    parser.add_argument("--force-ingest", action="store_true")
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
        if args.force_ingest or not _portfolio_exists(query_base_url, args.portfolio_id):
            payload = _build_portfolio_bundle_payload(bundle)
            _request_json("POST", f"{ingestion_base_url}/ingest/portfolio-bundle", payload=payload)
        _ingest_reference_data(ingestion_base_url, bundle)

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
