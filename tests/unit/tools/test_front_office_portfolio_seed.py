from datetime import date

from tools.front_office_portfolio_seed import (
    DEFAULT_BENCHMARK_ID,
    build_portfolio_seed_cleanup_sql,
    build_front_office_portfolio_bundle,
    build_front_office_seed_cleanup_sql,
)


def _build_bundle():
    return build_front_office_portfolio_bundle(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        start_date=date(2025, 3, 31),
        end_date=date(2026, 3, 28),
        benchmark_start_date=date(2025, 1, 6),
        benchmark_id=DEFAULT_BENCHMARK_ID,
    )


def test_front_office_bundle_uses_real_business_names_and_context():
    bundle = _build_bundle()

    portfolio = bundle["portfolios"][0]
    assert portfolio["portfolio_id"] == "PB_SG_GLOBAL_BAL_001"
    assert portfolio["client_id"] == "CIF_SG_000184"
    assert portfolio["advisor_id"] == "RM_SG_001"
    assert portfolio["portfolio_type"] == "discretionary"
    assert portfolio["booking_center_code"] == "Singapore"

    instrument_names = {instrument["name"] for instrument in bundle["instruments"]}
    assert "Apple Inc." in instrument_names
    assert "Microsoft Corporation" in instrument_names
    assert "Siemens Financieringsmaatschappij NV 2.500% 2031" in instrument_names
    assert "Private Credit Opportunities Fund A" in instrument_names
    assert all("MANUAL_" not in instrument["name"] for instrument in bundle["instruments"])


def test_front_office_bundle_carries_meaningful_classification_metadata():
    bundle = _build_bundle()
    by_security = {instrument["security_id"]: instrument for instrument in bundle["instruments"]}

    assert "portfolio_id" not in by_security["CASH_USD_BOOK_OPERATING"]
    assert "portfolio_id" not in by_security["CASH_EUR_BOOK_OPERATING"]
    assert by_security["FO_EQ_AAPL_US"]["sector"] == "Information Technology"
    assert by_security["FO_EQ_AAPL_US"]["issuer_name"] == "Apple Inc."
    assert by_security["FO_EQ_SAP_DE"]["country_of_risk"] == "Germany"
    assert by_security["FO_BOND_UST_2030"]["rating"] == "AA+"
    assert by_security["FO_ETF_MSCI_WORLD"]["liquidity_tier"] == "L1"
    assert by_security["FO_FUND_PIMCO_INC"]["liquidity_tier"] == "L3"
    assert (
        by_security["FO_BOND_SIEMENS_2031"]["ultimate_parent_issuer_name"]
        == "Siemens AG"
    )
    assert by_security["FO_PRIV_PRIVATE_CREDIT_A"]["liquidity_tier"] == "L5"
    assert by_security["FO_PRIV_PRIVATE_CREDIT_A"]["sector"] == "Private Credit"


def test_front_office_bundle_includes_income_and_paired_cash_transactions():
    bundle = _build_bundle()
    by_txn = {transaction["transaction_id"]: transaction for transaction in bundle["transactions"]}

    interest = by_txn["TXN-INT-UST-001"]
    assert interest["transaction_type"] == "INTEREST"
    assert interest["interest_direction"] == "INCOME"
    assert interest["withholding_tax_amount"] == "81.75"
    assert interest["other_interest_deductions_amount"] == "12.00"
    assert interest["net_interest_amount"] == "1187.00"

    dividend_cash_leg = by_txn["TXN-CASH-DIV-AAPL-001"]
    assert dividend_cash_leg["transaction_type"] == "BUY"
    assert dividend_cash_leg["security_id"] == "CASH_USD_BOOK_OPERATING"
    assert dividend_cash_leg["gross_transaction_amount"] == "850.00"

    planned_withdrawal = by_txn["TXN-WITHDRAWAL-PLANNED-001"]
    assert planned_withdrawal["transaction_type"] == "WITHDRAWAL"
    assert planned_withdrawal["settlement_date"] > planned_withdrawal["transaction_date"]
    future_withdrawal = by_txn["TXN-WITHDRAWAL-FUTURE-001"]
    assert future_withdrawal["transaction_type"] == "WITHDRAWAL"
    assert future_withdrawal["transaction_date"].startswith("2026-04-07")
    assert future_withdrawal["settlement_date"].startswith("2026-04-10")

    assert by_txn["TXN-CASH-BUY-AAPL-001"]["transaction_type"] == "SELL"
    assert by_txn["TXN-CASH-SELL-AAPL-001"]["transaction_type"] == "BUY"


def test_front_office_bundle_keeps_eur_sleeve_funded():
    bundle = _build_bundle()
    by_txn = {transaction["transaction_id"]: transaction for transaction in bundle["transactions"]}

    assert by_txn["TXN-DEP-EUR-001"]["gross_transaction_amount"] == "335000"

    eur_funding = float(by_txn["TXN-DEP-EUR-001"]["gross_transaction_amount"])
    eur_buys = sum(
        float(by_txn[txn_id]["gross_transaction_amount"])
        for txn_id in (
            "TXN-BUY-SAP-001",
            "TXN-BUY-BLK-ALLOC-001",
            "TXN-BUY-SIEMENS-BOND-001",
        )
    )
    assert eur_funding > eur_buys


def test_front_office_bundle_places_income_and_activity_inside_current_reporting_window():
    bundle = _build_bundle()
    by_txn = {transaction["transaction_id"]: transaction for transaction in bundle["transactions"]}

    assert by_txn["TXN-DIV-AAPL-001"]["transaction_date"].startswith("2026-03-03")
    assert by_txn["TXN-INT-UST-001"]["transaction_date"].startswith("2026-03-11")
    assert by_txn["TXN-DEP-USD-TOPUP-001"]["transaction_date"].startswith("2026-03-05")
    assert by_txn["TXN-FEE-ADVISORY-001"]["transaction_date"].startswith("2026-03-12")
    assert by_txn["TXN-SELL-AAPL-001"]["transaction_date"].startswith("2026-02-28")
    assert by_txn["TXN-WITHDRAWAL-PLANNED-001"]["transaction_date"].startswith("2026-03-26")


def test_front_office_bundle_includes_forward_cashflow_event_inside_projection_window():
    bundle = _build_bundle()
    future_txns = [
        transaction
        for transaction in bundle["transactions"]
        if transaction["transaction_date"][:10] > bundle["as_of_date"]
    ]

    assert future_txns
    assert {transaction["transaction_id"] for transaction in future_txns} == {
        "TXN-WITHDRAWAL-FUTURE-001"
    }
    assert future_txns[0]["settlement_date"].startswith("2026-04-10")


def test_front_office_bundle_carries_full_price_coverage_through_as_of_date():
    bundle = _build_bundle()

    private_credit_prices = [
        row
        for row in bundle["market_prices"]
        if row["security_id"] == "FO_PRIV_PRIVATE_CREDIT_A"
    ]
    assert private_credit_prices
    assert private_credit_prices[-1]["price_date"] == bundle["as_of_date"]

    benchmark_assignment = bundle["benchmark_assignments"][0]
    assert benchmark_assignment["portfolio_id"] == "PB_SG_GLOBAL_BAL_001"
    assert benchmark_assignment["benchmark_id"] == DEFAULT_BENCHMARK_ID
    assert benchmark_assignment["assignment_source"] == "front_office_portfolio_seed"


def test_front_office_bundle_extends_fx_coverage_through_forward_projection_window():
    bundle = _build_bundle()

    eur_usd_rates = [
        row
        for row in bundle["fx_rates"]
        if row["from_currency"] == "EUR" and row["to_currency"] == "USD"
    ]
    assert eur_usd_rates
    assert eur_usd_rates[-1]["rate_date"] == "2026-04-27"


def test_front_office_bundle_extends_usd_risk_free_coverage_through_forward_window():
    bundle = _build_bundle()

    risk_free_series = bundle["risk_free_series"]
    assert risk_free_series
    assert risk_free_series[0]["series_currency"] == "USD"
    assert risk_free_series[0]["risk_free_curve_id"] == "USD_SOFR_3M"
    assert risk_free_series[0]["source_vendor"] == "LOTUS_FRONT_OFFICE_SEED"
    assert risk_free_series[-1]["series_date"] == "2026-04-27"


def test_front_office_bundle_rewrites_all_benchmark_artifacts_to_dedicated_seed_identity():
    bundle = _build_bundle()

    assert {row["benchmark_id"] for row in bundle["benchmark_definitions"]} == {
        DEFAULT_BENCHMARK_ID
    }
    assert {row["benchmark_id"] for row in bundle["benchmark_compositions"]} == {
        DEFAULT_BENCHMARK_ID
    }
    assert {row["benchmark_id"] for row in bundle["benchmark_return_series"]} == {
        DEFAULT_BENCHMARK_ID
    }
    assert (
        bundle["benchmark_definitions"][0]["benchmark_name"]
        == "Private Banking Global Balanced 60/40"
    )
    assert bundle["benchmark_definitions"][0]["benchmark_provider"] == "LOTUS_FRONT_OFFICE_SEED"
    assert bundle["benchmark_definitions"][0]["source_vendor"] == "LOTUS_FRONT_OFFICE_SEED"
    assert bundle["benchmark_compositions"][0]["rebalance_event_id"].startswith(
        DEFAULT_BENCHMARK_ID.lower()
    )
    assert bundle["benchmark_return_series"][0]["series_id"].startswith(
        DEFAULT_BENCHMARK_ID.lower()
    )
    assert bundle["benchmark_return_series"][0]["source_record_id"].startswith(
        DEFAULT_BENCHMARK_ID.lower()
    )
    assert bundle["benchmark_return_series"][-1]["series_date"] == "2026-04-27"


def test_front_office_cleanup_sql_removes_benchmark_seed_rows_deterministically():
    sql = build_front_office_seed_cleanup_sql(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        benchmark_id=DEFAULT_BENCHMARK_ID,
    )

    assert "delete from portfolio_benchmark_assignments" in sql
    assert "delete from benchmark_composition_series" in sql
    assert "delete from benchmark_return_series" in sql
    assert "delete from benchmark_definitions" in sql
    assert "PB_SG_GLOBAL_BAL_001" in sql
    assert DEFAULT_BENCHMARK_ID in sql


def test_portfolio_seed_cleanup_sql_removes_portfolio_owned_state_before_reseed():
    sql = build_portfolio_seed_cleanup_sql(portfolio_id="PB_SG_GLOBAL_BAL_001")

    assert "delete from transactions where portfolio_id = 'PB_SG_GLOBAL_BAL_001';" in sql
    assert "delete from position_timeseries where portfolio_id = 'PB_SG_GLOBAL_BAL_001';" in sql
    assert "delete from cash_account_masters where portfolio_id = 'PB_SG_GLOBAL_BAL_001';" in sql
    assert "delete from portfolios where portfolio_id = 'PB_SG_GLOBAL_BAL_001';" in sql
    assert "delete from transaction_costs where transaction_id in" in sql
