import sys
from datetime import date
from decimal import Decimal

import pytest

import tools.front_office_seed_contract as front_office_seed_contract_module
from tools.front_office_portfolio_seed import (
    DEFAULT_BENCHMARK_ID,
    FRONT_OFFICE_EXPECTATION,
    FRONT_OFFICE_SEED_CONTRACT,
    _collect_front_office_readiness_diagnostics,
    _extract_readiness_summary,
    _extract_support_overview_summary,
    _front_office_analytics_are_fresh,
    _ingest_front_office_core_data,
    _reprocess_front_office_transactions,
    _required_cross_currency_fx_windows,
    _validate_front_office_cash_transactions,
    _validate_front_office_internal_transaction_pairs,
    _verify_front_office_portfolio,
    _wait_for_portfolio_persistence,
    _wait_for_required_fx_readiness,
    build_front_office_portfolio_bundle,
    build_front_office_seed_cleanup_sql,
    build_portfolio_seed_cleanup_sql,
    parse_args,
)
from tools.front_office_seed_contract import load_front_office_seed_contract


def _build_bundle():
    return build_front_office_portfolio_bundle(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        start_date=date(2025, 3, 31),
        end_date=date(2026, 4, 10),
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
    assert by_security["FO_BOND_SIEMENS_2031"]["ultimate_parent_issuer_name"] == "Siemens AG"
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
    assert future_withdrawal["transaction_date"].startswith("2026-04-17")
    assert future_withdrawal["settlement_date"].startswith("2026-04-20")

    assert by_txn["TXN-CASH-BUY-AAPL-001"]["transaction_type"] == "SELL"
    assert by_txn["TXN-CASH-SELL-AAPL-001"]["transaction_type"] == "BUY"
    assert by_txn["TXN-FEE-ADVISORY-001"]["transaction_type"] == "FEE"
    assert by_txn["TXN-FEE-ADVISORY-001"]["quantity"] == "275.00"
    assert by_txn["TXN-FEE-ADVISORY-001"]["price"] == "1"


def test_front_office_bundle_honors_explicit_end_date_for_market_prices():
    bundle = build_front_office_portfolio_bundle(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        start_date=date(2025, 3, 31),
        end_date=date(2026, 4, 17),
        benchmark_start_date=date(2025, 1, 6),
        benchmark_id=DEFAULT_BENCHMARK_ID,
    )

    aapl_prices = [
        row["price_date"]
        for row in bundle["market_prices"]
        if row["security_id"] == "FO_EQ_AAPL_US"
    ]
    cash_prices = [
        row["price_date"]
        for row in bundle["market_prices"]
        if row["security_id"] == "CASH_USD_BOOK_OPERATING"
    ]
    future_withdrawal = next(
        transaction
        for transaction in bundle["transactions"]
        if transaction["transaction_id"] == "TXN-WITHDRAWAL-FUTURE-001"
    )

    assert max(aapl_prices) == "2026-04-17"
    assert max(cash_prices) == "2026-04-17"
    assert future_withdrawal["transaction_date"].startswith("2026-04-24")
    assert future_withdrawal["settlement_date"].startswith("2026-04-27")


def test_front_office_bundle_pairs_internal_transactions_under_shared_event_linkage():
    bundle = _build_bundle()
    by_txn = {transaction["transaction_id"]: transaction for transaction in bundle["transactions"]}

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

    for product_transaction_id, cash_transaction_id in paired_transaction_ids:
        product_leg = by_txn[product_transaction_id]
        cash_leg = by_txn[cash_transaction_id]

        assert product_leg["economic_event_id"] == cash_leg["economic_event_id"]
        assert product_leg["linked_transaction_group_id"] == cash_leg["linked_transaction_group_id"]


def test_front_office_bundle_internal_pairs_economically_net_to_zero():
    bundle = _build_bundle()

    _validate_front_office_internal_transaction_pairs(bundle["transactions"])


def test_front_office_bundle_normalizes_cash_book_transaction_shape():
    bundle = _build_bundle()

    for transaction in bundle["transactions"]:
        if not transaction["security_id"].startswith("CASH_"):
            continue
        if transaction["transaction_type"] not in {"BUY", "SELL", "DEPOSIT", "WITHDRAWAL", "FEE"}:
            continue

        assert Decimal(transaction["price"]) == Decimal("1")
        assert Decimal(transaction["quantity"]) == Decimal(transaction["gross_transaction_amount"])
        assert transaction["currency"] == transaction["trade_currency"]


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


def test_front_office_bundle_populates_historical_fx_on_cross_currency_transactions():
    bundle = _build_bundle()
    by_txn = {transaction["transaction_id"]: transaction for transaction in bundle["transactions"]}

    cross_currency_transaction_ids = (
        "TXN-DEP-EUR-001",
        "TXN-BUY-SAP-001",
        "TXN-CASH-BUY-SAP-001",
        "TXN-BUY-BLK-ALLOC-001",
        "TXN-CASH-BUY-BLK-ALLOC-001",
        "TXN-BUY-SIEMENS-BOND-001",
        "TXN-CASH-BUY-SIEMENS-BOND-001",
    )

    for transaction_id in cross_currency_transaction_ids:
        assert Decimal(by_txn[transaction_id]["transaction_fx_rate"]) > Decimal("0")


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
    assert future_txns[0]["transaction_date"].startswith("2026-04-17")
    assert future_txns[0]["settlement_date"].startswith("2026-04-20")


def test_front_office_bundle_carries_full_price_coverage_through_as_of_date():
    bundle = _build_bundle()

    private_credit_prices = [
        row for row in bundle["market_prices"] if row["security_id"] == "FO_PRIV_PRIVATE_CREDIT_A"
    ]
    assert private_credit_prices
    assert private_credit_prices[-1]["price_date"] == bundle["as_of_date"]

    benchmark_assignment = bundle["benchmark_assignments"][0]
    assert benchmark_assignment["portfolio_id"] == "PB_SG_GLOBAL_BAL_001"
    assert benchmark_assignment["benchmark_id"] == DEFAULT_BENCHMARK_ID
    assert benchmark_assignment["assignment_source"] == "front_office_portfolio_seed"

    non_cash_security_ids = {
        instrument["security_id"]
        for instrument in bundle["instruments"]
        if instrument["asset_class"] != "Cash"
    }
    last_price_by_security = {
        security_id: max(
            row["price_date"]
            for row in bundle["market_prices"]
            if row["security_id"] == security_id
        )
        for security_id in non_cash_security_ids
    }
    assert last_price_by_security
    assert set(last_price_by_security) == non_cash_security_ids
    assert all(price_date == bundle["as_of_date"] for price_date in last_price_by_security.values())


def test_front_office_bundle_cash_economics_are_plausible_by_currency():
    bundle = _build_bundle()
    cash_security_ids = {
        account["security_id"]: account["account_currency"] for account in bundle["cash_accounts"]
    }
    cash_balance_by_currency = {currency: Decimal("0") for currency in cash_security_ids.values()}

    for transaction in bundle["transactions"]:
        currency = cash_security_ids.get(transaction["security_id"])
        if currency is None:
            continue
        amount = Decimal(transaction["gross_transaction_amount"])
        if transaction["transaction_type"] in {"DEPOSIT", "BUY"}:
            cash_balance_by_currency[currency] += amount
        elif transaction["transaction_type"] in {"SELL", "FEE", "WITHDRAWAL"}:
            cash_balance_by_currency[currency] -= amount
        else:
            raise AssertionError(
                f"Unexpected cash transaction type: {transaction['transaction_type']}"
            )

    assert cash_balance_by_currency["USD"] > Decimal("0")
    assert cash_balance_by_currency["EUR"] > Decimal("0")
    assert cash_balance_by_currency["USD"] == Decimal("101347.00")
    assert cash_balance_by_currency["EUR"] == Decimal("19805.50")


def test_front_office_cash_transaction_validator_rejects_non_normalized_cash_rows():
    bundle = _build_bundle()
    advisory_fee = next(
        transaction
        for transaction in bundle["transactions"]
        if transaction["transaction_id"] == "TXN-FEE-ADVISORY-001"
    )
    broken_fee = dict(advisory_fee, quantity="1", price="275.00")

    with pytest.raises(
        ValueError,
        match="TXN-FEE-ADVISORY-001 must use price=1 for cash-book transaction rows.",
    ):
        _validate_front_office_cash_transactions([broken_fee])


def test_front_office_bundle_extends_fx_coverage_through_forward_projection_window():
    bundle = _build_bundle()

    eur_usd_rates = [
        row
        for row in bundle["fx_rates"]
        if row["from_currency"] == "EUR" and row["to_currency"] == "USD"
    ]
    assert eur_usd_rates
    assert eur_usd_rates[-1]["rate_date"] == "2026-05-10"


def test_front_office_bundle_extends_usd_risk_free_coverage_through_forward_window():
    bundle = _build_bundle()

    risk_free_series = bundle["risk_free_series"]
    assert risk_free_series
    assert risk_free_series[0]["series_currency"] == "USD"
    assert risk_free_series[0]["risk_free_curve_id"] == "USD_SOFR_3M"
    assert risk_free_series[0]["source_vendor"] == "LOTUS_FRONT_OFFICE_SEED"
    assert risk_free_series[-1]["series_date"] == "2026-05-10"


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
    assert bundle["benchmark_return_series"][-1]["series_date"] == "2026-05-10"
    sector_by_index = {
        index["index_id"]: index["classification_labels"].get("sector")
        for index in bundle["indices"]
    }
    assert sector_by_index == {
        "IDX_GLOBAL_EQUITY_TR": "broad_market_equity",
        "IDX_GLOBAL_BOND_TR": "broad_market_fixed_income",
    }


def test_front_office_cleanup_sql_removes_benchmark_seed_rows_deterministically():
    sql = build_front_office_seed_cleanup_sql(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        benchmark_id=DEFAULT_BENCHMARK_ID,
    )

    assert "delete from portfolio_benchmark_assignments" in sql
    assert "delete from benchmark_composition_series" in sql
    assert "delete from benchmark_return_series" in sql
    assert "delete from benchmark_definitions" in sql
    assert "delete from index_price_series where index_id in" in sql
    assert "delete from index_return_series where index_id in" in sql
    assert "delete from index_definitions where index_id in" in sql
    assert "IDX_GLOBAL_EQUITY_TR" in sql
    assert "IDX_GLOBAL_BOND_TR" in sql
    assert "PB_SG_GLOBAL_BAL_001" in sql
    assert DEFAULT_BENCHMARK_ID in sql


def test_portfolio_seed_cleanup_sql_removes_portfolio_owned_state_before_reseed():
    sql = build_portfolio_seed_cleanup_sql(portfolio_id="PB_SG_GLOBAL_BAL_001")

    assert "delete from transactions where portfolio_id = 'PB_SG_GLOBAL_BAL_001';" in sql
    assert "delete from position_timeseries where portfolio_id = 'PB_SG_GLOBAL_BAL_001';" in sql
    assert "delete from cash_account_masters where portfolio_id = 'PB_SG_GLOBAL_BAL_001';" in sql
    assert "delete from portfolios where portfolio_id = 'PB_SG_GLOBAL_BAL_001';" in sql
    assert "delete from transaction_costs where transaction_id in" in sql
    assert "delete from reprocessing_jobs;" not in sql
    assert "service_name = 'position-calculator'" not in sql
    assert "event_id like 'transaction_processing.ready-%'" not in sql
    assert "event_id like 'transactions.cost.processed-%'" not in sql
    assert "service_name = 'cost-calculator'" not in sql
    assert "service_name = 'cashflow-calculator'" not in sql
    assert "service_name = 'pipeline-orchestrator-processed-txn'" not in sql
    assert "service_name = 'persistence-portfolios'" not in sql
    assert "event_id like 'portfolios.raw.received-%'" not in sql


def test_front_office_seed_ingests_core_data_in_parent_first_order(monkeypatch):
    bundle = _build_bundle()
    calls = []
    waits = []
    fx_waits = []

    def capture_request(method, url, *, payload=None):
        calls.append((method, url, payload))
        return 202, {"accepted_count": 1}

    def capture_wait(**kwargs):
        waits.append(kwargs)

    monkeypatch.setattr("tools.front_office_portfolio_seed._request_json", capture_request)
    monkeypatch.setattr(
        "tools.front_office_portfolio_seed._wait_for_portfolio_persistence",
        capture_wait,
    )
    monkeypatch.setattr(
        "tools.front_office_portfolio_seed._wait_for_required_fx_readiness",
        lambda **kwargs: fx_waits.append(kwargs),
    )

    _ingest_front_office_core_data(
        ingestion_base_url="http://ingestion.dev.lotus",
        query_base_url="http://query.dev.lotus",
        bundle=bundle,
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        wait_seconds=90,
        poll_interval_seconds=3,
    )

    assert [call[1] for call in calls] == [
        "http://ingestion.dev.lotus/ingest/business-dates",
        "http://ingestion.dev.lotus/ingest/portfolios",
        "http://ingestion.dev.lotus/ingest/instruments",
        "http://ingestion.dev.lotus/ingest/fx-rates",
        "http://ingestion.dev.lotus/ingest/market-prices",
        "http://ingestion.dev.lotus/ingest/transactions",
    ]
    assert waits == [
        {
            "query_base_url": "http://query.dev.lotus",
            "portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "wait_seconds": 90,
            "poll_interval_seconds": 3,
        }
    ]
    assert fx_waits == [
        {
            "query_base_url": "http://query.dev.lotus",
            "bundle": bundle,
            "wait_seconds": 90,
            "poll_interval_seconds": 3,
        }
    ]


def test_front_office_seed_derives_required_cross_currency_fx_windows():
    bundle = _build_bundle()

    assert _required_cross_currency_fx_windows(bundle) == [
        ("EUR", "USD", "2025-04-02", "2025-07-27")
    ]


def test_front_office_seed_waits_for_required_fx_readiness(monkeypatch):
    bundle = _build_bundle()
    observed_urls = []
    responses = iter(
        [
            (200, {"rates": [{"rate_date": "2025-04-20", "rate": "1.074352"}]}),
            (
                200,
                {
                    "rates": [
                        {"rate_date": "2025-04-02", "rate": "1.072685"},
                        {"rate_date": "2025-07-27", "rate": "1.081000"},
                    ]
                },
            ),
        ]
    )

    def fake_request(method, url, *, payload=None):
        observed_urls.append((method, url, payload))
        return next(responses)

    monkeypatch.setattr("tools.front_office_portfolio_seed._request_json", fake_request)
    monkeypatch.setattr("tools.front_office_portfolio_seed.time.sleep", lambda _: None)

    _wait_for_required_fx_readiness(
        query_base_url="http://query.dev.lotus",
        bundle=bundle,
        wait_seconds=1,
        poll_interval_seconds=0,
    )

    assert observed_urls == [
        (
            "GET",
            "http://query.dev.lotus/fx-rates/"
            "?from_currency=EUR&to_currency=USD&start_date=2025-04-02&end_date=2025-07-27",
            None,
        ),
        (
            "GET",
            "http://query.dev.lotus/fx-rates/"
            "?from_currency=EUR&to_currency=USD&start_date=2025-04-02&end_date=2025-07-27",
            None,
        ),
    ]


def test_front_office_seed_wait_for_required_fx_readiness_times_out(monkeypatch):
    bundle = _build_bundle()

    monkeypatch.setattr(
        "tools.front_office_portfolio_seed._request_json",
        lambda method, url, *, payload=None: (200, {"rates": []}),
    )
    monkeypatch.setattr("tools.front_office_portfolio_seed.time.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="Timed out waiting for FX readiness"):
        _wait_for_required_fx_readiness(
            query_base_url="http://query.dev.lotus",
            bundle=bundle,
            wait_seconds=0,
            poll_interval_seconds=0,
        )


def test_front_office_seed_verifies_against_canonical_gateway_by_default(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["front_office_portfolio_seed.py"])

    args = parse_args()

    assert args.gateway_base_url == "http://gateway.dev.lotus"
    assert args.end_date == "2026-04-10"


def test_front_office_seed_contract_loads_platform_governed_defaults() -> None:
    contract = load_front_office_seed_contract()

    assert contract.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert contract.benchmark_id == "BMK_PB_GLOBAL_BALANCED_60_40"
    assert contract.canonical_as_of_date == "2026-04-10"
    assert contract.seed_start_date == "2025-03-31"
    assert contract.benchmark_start_date == "2025-01-06"
    assert contract.min_transactions >= 30
    assert contract.min_risk_rolling_windows >= 4
    assert FRONT_OFFICE_SEED_CONTRACT == contract


def test_front_office_runtime_expectation_is_derived_from_contract() -> None:
    assert FRONT_OFFICE_EXPECTATION.portfolio_id == FRONT_OFFICE_SEED_CONTRACT.portfolio_id
    assert FRONT_OFFICE_EXPECTATION.min_transactions == FRONT_OFFICE_SEED_CONTRACT.min_transactions
    assert (
        FRONT_OFFICE_EXPECTATION.min_cash_accounts == FRONT_OFFICE_SEED_CONTRACT.min_cash_accounts
    )
    assert (
        FRONT_OFFICE_EXPECTATION.min_allocation_views
        == FRONT_OFFICE_SEED_CONTRACT.min_allocation_views
    )
    assert (
        FRONT_OFFICE_EXPECTATION.min_projected_cashflow_points
        == FRONT_OFFICE_SEED_CONTRACT.min_projected_cashflow_points
    )


def test_front_office_seed_contract_has_governed_fallback_when_platform_contract_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LOTUS_PLATFORM_REPO", raising=False)
    monkeypatch.setattr(
        front_office_seed_contract_module,
        "DEFAULT_PLATFORM_REPO",
        front_office_seed_contract_module.REPO_ROOT / "missing-platform-repo",
    )

    contract = load_front_office_seed_contract()

    assert contract.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert contract.benchmark_id == "BMK_PB_GLOBAL_BALANCED_60_40"
    assert contract.canonical_as_of_date == "2026-04-10"
    assert contract.min_transactions == 30


def test_front_office_seed_reprocesses_all_seed_transactions(monkeypatch):
    bundle = _build_bundle()
    calls = []

    def capture_request(method, url, *, payload=None):
        calls.append((method, url, payload))
        return 202, {"accepted_count": len(payload["transaction_ids"])}

    monkeypatch.setattr(
        "tools.front_office_portfolio_seed._request_json",
        capture_request,
    )

    _reprocess_front_office_transactions("http://ingestion.dev.lotus", bundle)

    assert calls == [
        (
            "POST",
            "http://ingestion.dev.lotus/reprocess/transactions",
            {
                "transaction_ids": [
                    transaction["transaction_id"] for transaction in bundle["transactions"]
                ]
            },
        )
    ]


def test_front_office_seed_waits_for_portfolio_persistence_before_reference_ingest(monkeypatch):
    observed_calls = []
    portfolio_exists_responses = iter([False, False, True])

    def fake_portfolio_exists(query_base_url: str, portfolio_id: str) -> bool:
        observed_calls.append((query_base_url, portfolio_id))
        return next(portfolio_exists_responses)

    monkeypatch.setattr(
        "tools.front_office_portfolio_seed._portfolio_exists",
        fake_portfolio_exists,
    )
    monkeypatch.setattr(
        "tools.front_office_portfolio_seed.time.sleep",
        lambda _: None,
    )

    _wait_for_portfolio_persistence(
        query_base_url="http://query.dev.lotus",
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        wait_seconds=3,
        poll_interval_seconds=0,
    )

    assert observed_calls == [
        ("http://query.dev.lotus", "PB_SG_GLOBAL_BAL_001"),
        ("http://query.dev.lotus", "PB_SG_GLOBAL_BAL_001"),
        ("http://query.dev.lotus", "PB_SG_GLOBAL_BAL_001"),
    ]


def test_front_office_seed_rejects_stale_derived_analytics_state():
    stale_reference = {"performance_end_date": "2025-08-05"}
    fresh_summary = {
        "report_end_date": "2026-04-11",
        "capabilities": {
            "return_path": {
                "latest_available_date": "2026-04-11",
            }
        },
    }

    assert not _front_office_analytics_are_fresh(
        analytics_reference=stale_reference,
        performance_summary=fresh_summary,
        expected_end_date="2026-04-10",
    )


def test_front_office_seed_accepts_current_derived_analytics_state():
    fresh_reference = {"performance_end_date": "2026-04-10"}
    fresh_summary = {
        "report_end_date": "2026-04-11",
        "capabilities": {
            "return_path": {
                "latest_available_date": "2026-04-11",
            }
        },
    }

    assert _front_office_analytics_are_fresh(
        analytics_reference=fresh_reference,
        performance_summary=fresh_summary,
        expected_end_date="2026-04-10",
    )


def test_extract_readiness_summary_surfaces_contract_relevant_state() -> None:
    payload = {
        "resolved_as_of_date": "2026-04-10",
        "holdings": {"status": "PENDING"},
        "pricing": {"status": "PENDING"},
        "transactions": {"status": "READY"},
        "reporting": {"status": "BLOCKED"},
        "blocking_reasons": [
            {"code": "SNAPSHOT_BEHIND_TRANSACTION_LEDGER"},
            {"code": "UNVALUED_POSITIONS_REMAIN"},
        ],
        "latest_booked_transaction_date": "2026-04-10",
        "latest_booked_position_snapshot_date": "2026-04-09",
        "snapshot_valuation_total_positions": 11,
        "snapshot_valuation_valued_positions": 10,
        "snapshot_valuation_unvalued_positions": 1,
        "missing_historical_fx_dependencies": {"missing_count": 0},
    }

    summary = _extract_readiness_summary(payload)

    assert summary["resolved_as_of_date"] == "2026-04-10"
    assert summary["holdings_status"] == "PENDING"
    assert summary["pricing_status"] == "PENDING"
    assert summary["reporting_status"] == "BLOCKED"
    assert summary["blocking_reason_codes"] == [
        "SNAPSHOT_BEHIND_TRANSACTION_LEDGER",
        "UNVALUED_POSITIONS_REMAIN",
    ]
    assert summary["snapshot_valuation_unvalued_positions"] == 1


def test_extract_support_overview_summary_surfaces_aggregation_backlog_signal() -> None:
    payload = {
        "pending_aggregation_jobs": 2,
        "processing_aggregation_jobs": 1,
        "stale_processing_aggregation_jobs": 0,
        "failed_aggregation_jobs": 0,
        "oldest_pending_aggregation_date": "2026-04-10",
        "latest_booked_transaction_date": "2026-04-10",
        "latest_booked_position_snapshot_date": "2026-04-09",
    }

    summary = _extract_support_overview_summary(payload)

    assert summary["pending_aggregation_jobs"] == 2
    assert summary["processing_aggregation_jobs"] == 1
    assert summary["oldest_pending_aggregation_date"] == "2026-04-10"
    assert summary["latest_booked_position_snapshot_date"] == "2026-04-09"


def test_collect_front_office_readiness_diagnostics_queries_support_endpoints(monkeypatch) -> None:
    responses = {
        "http://cp.dev/support/portfolios/P1/readiness?as_of_date=2026-04-10": (
            200,
            {
                "resolved_as_of_date": "2026-04-10",
                "holdings": {"status": "READY"},
                "pricing": {"status": "PENDING"},
                "transactions": {"status": "READY"},
                "reporting": {"status": "PENDING"},
                "blocking_reasons": [{"code": "UNVALUED_POSITIONS_REMAIN"}],
                "latest_booked_transaction_date": "2026-04-10",
                "latest_booked_position_snapshot_date": "2026-04-10",
                "snapshot_valuation_total_positions": 11,
                "snapshot_valuation_valued_positions": 10,
                "snapshot_valuation_unvalued_positions": 1,
                "missing_historical_fx_dependencies": {"missing_count": 0},
            },
        ),
        "http://cp.dev/support/portfolios/P1/overview": (
            200,
            {
                "pending_aggregation_jobs": 1,
                "processing_aggregation_jobs": 0,
                "stale_processing_aggregation_jobs": 0,
                "failed_aggregation_jobs": 0,
                "oldest_pending_aggregation_date": "2026-04-10",
                "latest_booked_transaction_date": "2026-04-10",
                "latest_booked_position_snapshot_date": "2026-04-09",
            },
        ),
        "http://cp.dev/support/portfolios/P1/aggregation-jobs?business_date=2026-04-10&limit=5": (
            200,
            {
                "total": 1,
                "items": [{"job_id": 4402, "status": "PENDING"}],
            },
        ),
    }

    def fake_request(method, url, *, payload=None):
        assert method == "GET"
        assert payload is None
        return responses[url]

    monkeypatch.setattr("tools.front_office_portfolio_seed._request_json", fake_request)

    diagnostics = _collect_front_office_readiness_diagnostics(
        query_control_plane_base_url="http://cp.dev",
        portfolio_id="P1",
        as_of_date="2026-04-10",
    )

    assert diagnostics["readiness"]["pricing_status"] == "PENDING"
    assert diagnostics["readiness"]["blocking_reason_codes"] == ["UNVALUED_POSITIONS_REMAIN"]
    assert diagnostics["support_overview"]["pending_aggregation_jobs"] == 1
    assert diagnostics["aggregation_jobs"]["job_ids"] == [4402]
    assert diagnostics["aggregation_jobs"]["statuses"] == ["PENDING"]


def test_front_office_seed_verification_counts_projected_transactions(monkeypatch) -> None:
    requested_urls: list[str] = []
    responses = {
        "http://query.dev/portfolios/P1/positions?as_of_date=2026-04-10": (
            200,
            {
                "data_quality_status": "COMPLETE",
                "positions": [
                    {"security_id": "SEC-1", "valuation": {"market_value": "100"}},
                    {"security_id": "SEC-2", "valuation": {"market_value": "200"}},
                ]
            },
        ),
        "http://query.dev/portfolios/P1/transactions?limit=300&include_projected=true": (
            200,
            {
                "total": 30,
                "transactions": [
                    {
                        "transaction_id": "TXN-DIV-1",
                        "transaction_date": "2026-03-03T09:00:00Z",
                        "transaction_type": "DIVIDEND",
                        "withholding_tax_amount": "5.00",
                    },
                    {
                        "transaction_id": "TXN-INT-1",
                        "transaction_date": "2026-03-11T09:00:00Z",
                        "transaction_type": "INTEREST",
                    },
                    {
                        "transaction_id": "TXN-DEP-1",
                        "transaction_date": "2026-03-05T09:00:00Z",
                        "transaction_type": "DEPOSIT",
                    },
                    {
                        "transaction_id": "TXN-FEE-1",
                        "transaction_date": "2026-03-12T09:00:00Z",
                        "transaction_type": "FEE",
                    },
                ],
            },
        ),
        "http://query.dev/reporting/asset-allocation/query": (
            200,
            {"views": [{"id": "asset_class"}, {"id": "sector"}]},
        ),
        (
            "http://query.dev/portfolios/P1/cash-balances"
            "?as_of_date=2026-04-10&reporting_currency=USD"
        ): (
            200,
            {
                "data_quality_status": "COMPLETE",
                "cash_accounts": [{"id": "USD"}, {"id": "EUR"}],
            },
        ),
        "http://cp.dev/integration/portfolios/P1/benchmark-assignment": (
            200,
            {"benchmark_id": "BMK-1"},
        ),
        "http://cp.dev/integration/portfolios/P1/analytics/reference": (
            200,
            {"performance_end_date": "2026-04-10"},
        ),
        "http://cp.dev/support/portfolios/P1/overview": (
            200,
            {
                "pending_valuation_jobs": 0,
                "processing_valuation_jobs": 0,
                "pending_aggregation_jobs": 0,
                "processing_aggregation_jobs": 0,
            },
        ),
        (
            "http://query.dev/portfolios/P1/cashflow-projection"
            "?as_of_date=2026-04-10&horizon_days=30&include_projected=true"
        ): (
            200,
            {"points": [{"net_cashflow": "100.00"}]},
        ),
        (
            "http://gateway.dev/api/v1/workbench/P1/performance/summary"
            "?period=YTD&chart_frequency=monthly&contribution_dimension=asset_class"
            "&attribution_dimension=asset_class&detail_basis=NET"
        ): (
            200,
            {
                "benchmark_code": "BMK-1",
                "report_end_date": "2026-04-12",
                "capabilities": {"return_path": {"latest_available_date": "2026-04-12"}},
            },
        ),
    }

    def fake_request(method, url, *, payload=None):
        requested_urls.append(url)
        return responses[url]

    monkeypatch.setattr("tools.front_office_portfolio_seed._request_json", fake_request)

    verification = _verify_front_office_portfolio(
        query_base_url="http://query.dev",
        query_control_plane_base_url="http://cp.dev",
        gateway_base_url="http://gateway.dev",
        expected=FRONT_OFFICE_EXPECTATION.__class__(
            portfolio_id="P1",
            min_positions=2,
            min_valued_positions=2,
            min_transactions=30,
            min_cash_accounts=2,
            min_allocation_views=2,
            min_projected_cashflow_points=1,
        ),
        as_of_date="2026-04-10",
        end_date="2026-04-10",
        wait_seconds=1,
        poll_interval_seconds=1,
    )

    assert verification["transactions"] == 30
    assert verification["income_types"] == 2
    assert verification["activity_buckets"] == 3
    assert verification["positions_data_quality_status"] == "COMPLETE"
    assert verification["pending_aggregation_jobs"] == 0
    assert any("include_projected=true" in url for url in requested_urls)
    assert all("income-summary/query" not in url for url in requested_urls)
    assert all("activity-summary/query" not in url for url in requested_urls)
