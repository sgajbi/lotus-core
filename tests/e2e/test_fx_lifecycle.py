import pytest

from .api_client import E2EApiClient
from .data_factory import unique_suffix


@pytest.fixture(scope="module")
def setup_fx_lifecycle_data(clean_db_module, e2e_api_client: E2EApiClient):
    suffix = unique_suffix()
    portfolio_id = f"E2E_FX_{suffix}"
    final_business_date = "2026-01-09"
    cash_usd = f"CASH_USD_FX_{suffix}"
    cash_eur = f"CASH_EUR_FX_{suffix}"
    cash_gbp = f"CASH_GBP_FX_{suffix}"

    forward_contract_id = f"FXC-{portfolio_id}-FWD-001"
    swap_event_id = f"FXSWAP-{portfolio_id}-001"
    swap_near_group_id = f"{swap_event_id}-NEAR"
    swap_far_group_id = f"{swap_event_id}-FAR"
    swap_contract_id = f"FXC-{swap_far_group_id}"

    portfolio_payload = {
        "portfolios": [
            {
                "portfolio_id": portfolio_id,
                "base_currency": "USD",
                "open_date": "2026-01-01",
                "risk_exposure": "Moderate",
                "investment_time_horizon": "Medium",
                "portfolio_type": "Discretionary",
                "booking_center_code": "SG",
                "client_id": f"E2E_FX_CIF_{suffix}",
                "status": "ACTIVE",
            }
        ]
    }
    instruments_payload = {
        "instruments": [
            {
                "security_id": cash_usd,
                "name": "US Dollar Cash",
                "isin": f"CASH_USD_FX_E2E_{suffix}",
                "currency": "USD",
                "product_type": "Cash",
                "asset_class": "Cash",
            },
            {
                "security_id": cash_eur,
                "name": "Euro Cash",
                "isin": f"CASH_EUR_FX_E2E_{suffix}",
                "currency": "EUR",
                "product_type": "Cash",
                "asset_class": "Cash",
            },
            {
                "security_id": cash_gbp,
                "name": "British Pound Cash",
                "isin": f"CASH_GBP_FX_E2E_{suffix}",
                "currency": "GBP",
                "product_type": "Cash",
                "asset_class": "Cash",
            },
        ]
    }
    business_dates_payload = {
        "business_dates": [
            {"business_date": "2026-01-02"},
            {"business_date": "2026-01-03"},
            {"business_date": "2026-01-06"},
            {"business_date": final_business_date},
        ]
    }
    fx_rates_payload = {
        "fx_rates": [
            {
                "from_currency": "EUR",
                "to_currency": "USD",
                "rate_date": "2026-01-02",
                "rate": 1.10,
            },
            {
                "from_currency": "EUR",
                "to_currency": "USD",
                "rate_date": "2026-01-03",
                "rate": 1.12,
            },
            {
                "from_currency": "EUR",
                "to_currency": "USD",
                "rate_date": final_business_date,
                "rate": 1.14,
            },
            {
                "from_currency": "GBP",
                "to_currency": "USD",
                "rate_date": "2026-01-06",
                "rate": 1.30,
            },
            {
                "from_currency": "GBP",
                "to_currency": "USD",
                "rate_date": final_business_date,
                "rate": 1.29,
            },
        ]
    }
    market_prices_payload = {
        "market_prices": [
            {
                "security_id": cash_usd,
                "price_date": final_business_date,
                "price": 1,
                "currency": "USD",
            },
            {
                "security_id": cash_eur,
                "price_date": final_business_date,
                "price": 1,
                "currency": "EUR",
            },
            {
                "security_id": cash_gbp,
                "price_date": final_business_date,
                "price": 1,
                "currency": "GBP",
            },
        ]
    }
    transactions_payload = {
        "transactions": [
            {
                "transaction_id": f"{portfolio_id}_SPOT_BUY_USD",
                "portfolio_id": portfolio_id,
                "instrument_id": cash_usd,
                "security_id": cash_usd,
                "transaction_date": "2026-01-02T09:00:00Z",
                "settlement_date": "2026-01-02T09:00:00Z",
                "transaction_type": "FX_SPOT",
                "component_type": "FX_CASH_SETTLEMENT_BUY",
                "component_id": "FXSPOT-001-BUY",
                "economic_event_id": f"EVT-{portfolio_id}-FXSPOT-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXSPOT-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 110000,
                "trade_currency": "USD",
                "currency": "USD",
                "fx_cash_leg_role": "BUY",
                "linked_fx_cash_leg_id": f"{portfolio_id}_SPOT_SELL_EUR",
                "settlement_status": "SETTLED",
                "pair_base_currency": "EUR",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "USD",
                "sell_currency": "EUR",
                "buy_amount": 110000,
                "sell_amount": 100000,
                "contract_rate": 1.10,
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_SPOT_SELL_EUR",
                "portfolio_id": portfolio_id,
                "instrument_id": cash_eur,
                "security_id": cash_eur,
                "transaction_date": "2026-01-02T09:00:00Z",
                "settlement_date": "2026-01-02T09:00:00Z",
                "transaction_type": "FX_SPOT",
                "component_type": "FX_CASH_SETTLEMENT_SELL",
                "component_id": "FXSPOT-001-SELL",
                "economic_event_id": f"EVT-{portfolio_id}-FXSPOT-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXSPOT-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 100000,
                "trade_currency": "EUR",
                "currency": "EUR",
                "fx_cash_leg_role": "SELL",
                "linked_fx_cash_leg_id": f"{portfolio_id}_SPOT_BUY_USD",
                "settlement_status": "SETTLED",
                "pair_base_currency": "EUR",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "USD",
                "sell_currency": "EUR",
                "buy_amount": 110000,
                "sell_amount": 100000,
                "contract_rate": 1.10,
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_FWD_OPEN",
                "portfolio_id": portfolio_id,
                "instrument_id": forward_contract_id,
                "security_id": forward_contract_id,
                "transaction_date": "2026-01-02T10:00:00Z",
                "settlement_date": "2026-01-06T10:00:00Z",
                "transaction_type": "FX_FORWARD",
                "component_type": "FX_CONTRACT_OPEN",
                "component_id": "FXFWD-001-OPEN",
                "economic_event_id": f"EVT-{portfolio_id}-FXFWD-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXFWD-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 260000,
                "trade_currency": "USD",
                "currency": "USD",
                "pair_base_currency": "GBP",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "USD",
                "sell_currency": "GBP",
                "buy_amount": 260000,
                "sell_amount": 200000,
                "contract_rate": 1.30,
                "fx_contract_id": forward_contract_id,
                "fx_contract_open_transaction_id": f"{portfolio_id}_FWD_OPEN",
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_FWD_BUY_USD",
                "portfolio_id": portfolio_id,
                "instrument_id": cash_usd,
                "security_id": cash_usd,
                "transaction_date": "2026-01-06T10:00:00Z",
                "settlement_date": "2026-01-06T10:00:00Z",
                "transaction_type": "FX_FORWARD",
                "component_type": "FX_CASH_SETTLEMENT_BUY",
                "component_id": "FXFWD-001-BUY",
                "economic_event_id": f"EVT-{portfolio_id}-FXFWD-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXFWD-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 260000,
                "trade_currency": "USD",
                "currency": "USD",
                "fx_cash_leg_role": "BUY",
                "linked_fx_cash_leg_id": f"{portfolio_id}_FWD_SELL_GBP",
                "settlement_status": "SETTLED",
                "pair_base_currency": "GBP",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "USD",
                "sell_currency": "GBP",
                "buy_amount": 260000,
                "sell_amount": 200000,
                "contract_rate": 1.30,
                "fx_contract_id": forward_contract_id,
                "settlement_of_fx_contract_id": forward_contract_id,
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_FWD_SELL_GBP",
                "portfolio_id": portfolio_id,
                "instrument_id": cash_gbp,
                "security_id": cash_gbp,
                "transaction_date": "2026-01-06T10:00:00Z",
                "settlement_date": "2026-01-06T10:00:00Z",
                "transaction_type": "FX_FORWARD",
                "component_type": "FX_CASH_SETTLEMENT_SELL",
                "component_id": "FXFWD-001-SELL",
                "economic_event_id": f"EVT-{portfolio_id}-FXFWD-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXFWD-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 200000,
                "trade_currency": "GBP",
                "currency": "GBP",
                "fx_cash_leg_role": "SELL",
                "linked_fx_cash_leg_id": f"{portfolio_id}_FWD_BUY_USD",
                "settlement_status": "SETTLED",
                "pair_base_currency": "GBP",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "USD",
                "sell_currency": "GBP",
                "buy_amount": 260000,
                "sell_amount": 200000,
                "contract_rate": 1.30,
                "fx_contract_id": forward_contract_id,
                "settlement_of_fx_contract_id": forward_contract_id,
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_FWD_CLOSE",
                "portfolio_id": portfolio_id,
                "instrument_id": forward_contract_id,
                "security_id": forward_contract_id,
                "transaction_date": "2026-01-06T10:00:00Z",
                "settlement_date": "2026-01-06T10:00:00Z",
                "transaction_type": "FX_FORWARD",
                "component_type": "FX_CONTRACT_CLOSE",
                "component_id": "FXFWD-001-CLOSE",
                "economic_event_id": f"EVT-{portfolio_id}-FXFWD-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXFWD-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 260000,
                "trade_currency": "USD",
                "currency": "USD",
                "pair_base_currency": "GBP",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "USD",
                "sell_currency": "GBP",
                "buy_amount": 260000,
                "sell_amount": 200000,
                "contract_rate": 1.30,
                "fx_contract_id": forward_contract_id,
                "fx_contract_open_transaction_id": f"{portfolio_id}_FWD_OPEN",
                "fx_contract_close_transaction_id": f"{portfolio_id}_FWD_CLOSE",
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_SWAP_OPEN",
                "portfolio_id": portfolio_id,
                "instrument_id": swap_contract_id,
                "security_id": swap_contract_id,
                "transaction_date": "2026-01-03T11:00:00Z",
                "settlement_date": "2026-01-09T11:00:00Z",
                "transaction_type": "FX_SWAP",
                "component_type": "FX_CONTRACT_OPEN",
                "component_id": "FXSWAP-001-OPEN",
                "economic_event_id": f"EVT-{portfolio_id}-FXSWAP-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXSWAP-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 57000,
                "trade_currency": "USD",
                "currency": "USD",
                "pair_base_currency": "EUR",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "EUR",
                "sell_currency": "USD",
                "buy_amount": 50000,
                "sell_amount": 57000,
                "contract_rate": 1.14,
                "fx_contract_id": swap_contract_id,
                "fx_contract_open_transaction_id": f"{portfolio_id}_SWAP_OPEN",
                "swap_event_id": swap_event_id,
                "near_leg_group_id": swap_near_group_id,
                "far_leg_group_id": swap_far_group_id,
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_SWAP_NEAR_BUY_USD",
                "portfolio_id": portfolio_id,
                "instrument_id": cash_usd,
                "security_id": cash_usd,
                "transaction_date": "2026-01-03T11:00:00Z",
                "settlement_date": "2026-01-03T11:00:00Z",
                "transaction_type": "FX_SWAP",
                "component_type": "FX_CASH_SETTLEMENT_BUY",
                "component_id": "FXSWAP-001-NEAR-BUY",
                "economic_event_id": f"EVT-{portfolio_id}-FXSWAP-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXSWAP-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 56000,
                "trade_currency": "USD",
                "currency": "USD",
                "fx_cash_leg_role": "BUY",
                "linked_fx_cash_leg_id": f"{portfolio_id}_SWAP_NEAR_SELL_EUR",
                "settlement_status": "SETTLED",
                "pair_base_currency": "EUR",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "USD",
                "sell_currency": "EUR",
                "buy_amount": 56000,
                "sell_amount": 50000,
                "contract_rate": 1.12,
                "fx_contract_id": swap_contract_id,
                "settlement_of_fx_contract_id": swap_contract_id,
                "swap_event_id": swap_event_id,
                "near_leg_group_id": swap_near_group_id,
                "far_leg_group_id": swap_far_group_id,
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_SWAP_NEAR_SELL_EUR",
                "portfolio_id": portfolio_id,
                "instrument_id": cash_eur,
                "security_id": cash_eur,
                "transaction_date": "2026-01-03T11:00:00Z",
                "settlement_date": "2026-01-03T11:00:00Z",
                "transaction_type": "FX_SWAP",
                "component_type": "FX_CASH_SETTLEMENT_SELL",
                "component_id": "FXSWAP-001-NEAR-SELL",
                "economic_event_id": f"EVT-{portfolio_id}-FXSWAP-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXSWAP-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 50000,
                "trade_currency": "EUR",
                "currency": "EUR",
                "fx_cash_leg_role": "SELL",
                "linked_fx_cash_leg_id": f"{portfolio_id}_SWAP_NEAR_BUY_USD",
                "settlement_status": "SETTLED",
                "pair_base_currency": "EUR",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "USD",
                "sell_currency": "EUR",
                "buy_amount": 56000,
                "sell_amount": 50000,
                "contract_rate": 1.12,
                "fx_contract_id": swap_contract_id,
                "settlement_of_fx_contract_id": swap_contract_id,
                "swap_event_id": swap_event_id,
                "near_leg_group_id": swap_near_group_id,
                "far_leg_group_id": swap_far_group_id,
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_SWAP_FAR_BUY_EUR",
                "portfolio_id": portfolio_id,
                "instrument_id": cash_eur,
                "security_id": cash_eur,
                "transaction_date": "2026-01-09T11:00:00Z",
                "settlement_date": "2026-01-09T11:00:00Z",
                "transaction_type": "FX_SWAP",
                "component_type": "FX_CASH_SETTLEMENT_BUY",
                "component_id": "FXSWAP-001-FAR-BUY",
                "economic_event_id": f"EVT-{portfolio_id}-FXSWAP-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXSWAP-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 50000,
                "trade_currency": "EUR",
                "currency": "EUR",
                "fx_cash_leg_role": "BUY",
                "linked_fx_cash_leg_id": f"{portfolio_id}_SWAP_FAR_SELL_USD",
                "settlement_status": "SETTLED",
                "pair_base_currency": "EUR",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "EUR",
                "sell_currency": "USD",
                "buy_amount": 50000,
                "sell_amount": 57000,
                "contract_rate": 1.14,
                "fx_contract_id": swap_contract_id,
                "settlement_of_fx_contract_id": swap_contract_id,
                "swap_event_id": swap_event_id,
                "near_leg_group_id": swap_near_group_id,
                "far_leg_group_id": swap_far_group_id,
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_SWAP_FAR_SELL_USD",
                "portfolio_id": portfolio_id,
                "instrument_id": cash_usd,
                "security_id": cash_usd,
                "transaction_date": "2026-01-09T11:00:00Z",
                "settlement_date": "2026-01-09T11:00:00Z",
                "transaction_type": "FX_SWAP",
                "component_type": "FX_CASH_SETTLEMENT_SELL",
                "component_id": "FXSWAP-001-FAR-SELL",
                "economic_event_id": f"EVT-{portfolio_id}-FXSWAP-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXSWAP-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 57000,
                "trade_currency": "USD",
                "currency": "USD",
                "fx_cash_leg_role": "SELL",
                "linked_fx_cash_leg_id": f"{portfolio_id}_SWAP_FAR_BUY_EUR",
                "settlement_status": "SETTLED",
                "pair_base_currency": "EUR",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "EUR",
                "sell_currency": "USD",
                "buy_amount": 50000,
                "sell_amount": 57000,
                "contract_rate": 1.14,
                "fx_contract_id": swap_contract_id,
                "settlement_of_fx_contract_id": swap_contract_id,
                "swap_event_id": swap_event_id,
                "near_leg_group_id": swap_near_group_id,
                "far_leg_group_id": swap_far_group_id,
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
            {
                "transaction_id": f"{portfolio_id}_SWAP_CLOSE",
                "portfolio_id": portfolio_id,
                "instrument_id": swap_contract_id,
                "security_id": swap_contract_id,
                "transaction_date": "2026-01-09T11:00:00Z",
                "settlement_date": "2026-01-09T11:00:00Z",
                "transaction_type": "FX_SWAP",
                "component_type": "FX_CONTRACT_CLOSE",
                "component_id": "FXSWAP-001-CLOSE",
                "economic_event_id": f"EVT-{portfolio_id}-FXSWAP-001",
                "linked_transaction_group_id": f"LTG-{portfolio_id}-FXSWAP-001",
                "calculation_policy_id": "FX_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
                "quantity": 0,
                "price": 0,
                "gross_transaction_amount": 57000,
                "trade_currency": "USD",
                "currency": "USD",
                "pair_base_currency": "EUR",
                "pair_quote_currency": "USD",
                "fx_rate_quote_convention": "QUOTE_PER_BASE",
                "buy_currency": "EUR",
                "sell_currency": "USD",
                "buy_amount": 50000,
                "sell_amount": 57000,
                "contract_rate": 1.14,
                "fx_contract_id": swap_contract_id,
                "fx_contract_open_transaction_id": f"{portfolio_id}_SWAP_OPEN",
                "fx_contract_close_transaction_id": f"{portfolio_id}_SWAP_CLOSE",
                "swap_event_id": swap_event_id,
                "near_leg_group_id": swap_near_group_id,
                "far_leg_group_id": swap_far_group_id,
                "spot_exposure_model": "NONE",
                "fx_realized_pnl_mode": "NONE",
            },
        ]
    }

    assert e2e_api_client.ingest("/ingest/portfolios", portfolio_payload).status_code == 202
    assert e2e_api_client.ingest("/ingest/instruments", instruments_payload).status_code == 202
    assert (
        e2e_api_client.ingest("/ingest/business-dates", business_dates_payload).status_code == 202
    )
    assert e2e_api_client.ingest("/ingest/fx-rates", fx_rates_payload).status_code == 202
    assert e2e_api_client.ingest("/ingest/transactions", transactions_payload).status_code == 202
    assert e2e_api_client.ingest("/ingest/market-prices", market_prices_payload).status_code == 202

    e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/transactions?transaction_type=FX_SWAP",
        lambda data: data.get("total") == 6,
        timeout=300,
        fail_message="FX swap lifecycle transactions did not materialize in query service.",
    )

    return {
        "portfolio_id": portfolio_id,
        "forward_contract_id": forward_contract_id,
        "swap_contract_id": swap_contract_id,
        "swap_event_id": swap_event_id,
        "swap_near_group_id": swap_near_group_id,
        "swap_far_group_id": swap_far_group_id,
        "cash_usd": cash_usd,
        "cash_eur": cash_eur,
        "cash_gbp": cash_gbp,
        "final_business_date": final_business_date,
    }


def test_fx_lifecycle_transactions_cover_spot_forward_and_swap(
    setup_fx_lifecycle_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_fx_lifecycle_data["portfolio_id"]
    forward_contract_id = setup_fx_lifecycle_data["forward_contract_id"]
    swap_contract_id = setup_fx_lifecycle_data["swap_contract_id"]
    swap_event_id = setup_fx_lifecycle_data["swap_event_id"]
    swap_near_group_id = setup_fx_lifecycle_data["swap_near_group_id"]
    swap_far_group_id = setup_fx_lifecycle_data["swap_far_group_id"]

    spot_rows = e2e_api_client.query(
        f"/portfolios/{portfolio_id}/transactions?transaction_type=FX_SPOT"
    ).json()
    assert spot_rows["total"] == 2
    assert {row["component_type"] for row in spot_rows["transactions"]} == {
        "FX_CASH_SETTLEMENT_BUY",
        "FX_CASH_SETTLEMENT_SELL",
    }

    forward_rows = e2e_api_client.query(
        f"/portfolios/{portfolio_id}/transactions?fx_contract_id={forward_contract_id}"
    ).json()
    assert forward_rows["total"] == 4
    assert {row["component_type"] for row in forward_rows["transactions"]} == {
        "FX_CONTRACT_OPEN",
        "FX_CONTRACT_CLOSE",
        "FX_CASH_SETTLEMENT_BUY",
        "FX_CASH_SETTLEMENT_SELL",
    }

    swap_rows = e2e_api_client.query(
        f"/portfolios/{portfolio_id}/transactions?swap_event_id={swap_event_id}"
    ).json()
    assert swap_rows["total"] == 6
    assert {row["fx_contract_id"] for row in swap_rows["transactions"]} == {swap_contract_id}
    assert {row["near_leg_group_id"] for row in swap_rows["transactions"]} == {swap_near_group_id}
    assert {row["far_leg_group_id"] for row in swap_rows["transactions"]} == {swap_far_group_id}


def test_fx_lifecycle_position_history_tracks_contract_open_and_close(
    setup_fx_lifecycle_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_fx_lifecycle_data["portfolio_id"]
    forward_contract_id = setup_fx_lifecycle_data["forward_contract_id"]
    swap_contract_id = setup_fx_lifecycle_data["swap_contract_id"]

    forward_history = e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/position-history?security_id={forward_contract_id}",
        lambda data: len(data.get("positions", [])) >= 2,
        timeout=300,
        fail_message="Forward FX contract history did not materialize.",
    )
    assert [row["quantity"] for row in forward_history["positions"]] == [1.0, 0.0]

    swap_history = e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/position-history?security_id={swap_contract_id}",
        lambda data: len(data.get("positions", [])) >= 2,
        timeout=300,
        fail_message="Swap FX contract history did not materialize.",
    )
    assert [row["quantity"] for row in swap_history["positions"]] == [1.0, 0.0]


def test_fx_lifecycle_cash_positions_reflect_settlement_pairs(
    setup_fx_lifecycle_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_fx_lifecycle_data["portfolio_id"]
    cash_usd = setup_fx_lifecycle_data["cash_usd"]
    cash_eur = setup_fx_lifecycle_data["cash_eur"]
    cash_gbp = setup_fx_lifecycle_data["cash_gbp"]
    final_business_date = setup_fx_lifecycle_data["final_business_date"]

    def _has_expected_cash_state(data: dict) -> bool:
        by_security = {position["security_id"]: position for position in data.get("positions", [])}
        required = {cash_usd, cash_eur, cash_gbp}
        if not required.issubset(set(by_security)):
            return False

        return (
            by_security[cash_usd]["quantity"] == pytest.approx(369000.0)
            and by_security[cash_eur]["quantity"] == pytest.approx(-100000.0)
            and by_security[cash_gbp]["quantity"] == pytest.approx(-200000.0)
        )

    positions = e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/positions?as_of_date={final_business_date}",
        _has_expected_cash_state,
        timeout=300,
        fail_message="FX cash positions did not converge to the expected settlement state.",
    )

    by_security = {position["security_id"]: position for position in positions["positions"]}
    assert by_security[cash_usd]["quantity"] == pytest.approx(369000.0)
    assert by_security[cash_eur]["quantity"] == pytest.approx(-100000.0)
    assert by_security[cash_gbp]["quantity"] == pytest.approx(-200000.0)
