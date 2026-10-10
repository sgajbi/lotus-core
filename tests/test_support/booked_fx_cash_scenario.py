"""Synthetic source-owned inputs admitted only through the registered HTTP APIs."""

import hashlib
import json

from tests.test_support.booked_fx_cash_oracle import FIRST_DAY, LAST_DAY


def seed_scenario(client, suffix, *, admit_instruments, same_currency=False):
    trade_currency, booked_fx = ("USD", "1") if same_currency else ("XTS", "2")
    portfolio, equity, cash = (f"FX1158_{name}_{suffix}" for name in ("P", "EQ", "CASH"))
    book = f"SYNTHETIC_FX_BOOK_{suffix}"
    client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolio_id": portfolio,
                    "base_currency": "USD",
                    "legal_book_id": book,
                    "open_date": FIRST_DAY,
                    "cost_basis_method": "FIFO",
                    "status": "ACTIVE",
                    "risk_exposure": "Synthetic",
                    "investment_time_horizon": "Synthetic",
                    "portfolio_type": "Synthetic",
                    "booking_center_code": "SG",
                    "client_id": f"FX1158_CLIENT_{suffix}",
                }
            ]
        },
    )
    client.wait_for_admitted_portfolio(portfolio)
    admit_instruments(client, equity, cash, trade_currency)
    client.ingest(
        "/ingest/reference/cash-accounts",
        {
            "cash_accounts": [
                {
                    "cash_account_id": cash,
                    "portfolio_id": portfolio,
                    "security_id": cash,
                    "display_name": f"Synthetic {trade_currency} settlement",
                    "account_currency": trade_currency,
                    "lifecycle_status": "ACTIVE",
                    "opened_on": FIRST_DAY,
                    "source_system": "SYNTHETIC_FX_ACCEPTANCE",
                    "source_record_id": cash,
                }
            ]
        },
    )
    assignments, facts = [], []
    for security in (equity, cash):
        assignments.append(
            {
                "tenant_id": client.tenant_id,
                "legal_book_id": book,
                "security_id": security,
                "policy_id": "UNIT_PRICE_MARKET_VALUE",
                "policy_version": 1,
                "valid_from": FIRST_DAY,
                "assignment_status": "ACTIVE",
                "assignment_version": 1,
                "source_system": "SYNTHETIC_FX_ACCEPTANCE",
                "source_record_id": f"POLICY_{security}",
                "source_revision": "1",
                "observed_at": f"{FIRST_DAY}T09:00:00Z",
                "assignment_reason": "Explicit synthetic unit-price financial acceptance",
            }
        )
        for day in (FIRST_DAY, LAST_DAY):
            price = "1" if security == cash else "100" if day == FIRST_DAY else "110"
            source = {"security": security, "day": day, "price": price, "currency": trade_currency}
            facts.append(
                {
                    "tenant_id": client.tenant_id,
                    "legal_book_id": book,
                    "security_id": security,
                    "price_date": day,
                    "price": price,
                    "currency": trade_currency,
                    "quote_basis": "UNIT_PRICE",
                    "fact_status": "ACTIVE",
                    "fact_version": 1,
                    "source_system": "SYNTHETIC_FX_ACCEPTANCE",
                    "source_record_id": f"PX_{security}_{day}",
                    "source_revision": "1",
                    "observed_at": f"{day}T09:00:00Z",
                    "source_content_hash": hashlib.sha256(
                        json.dumps(source, sort_keys=True).encode()
                    ).hexdigest(),
                }
            )
    client.ingest(
        "/ingest/instrument-valuation-policy-assignments",
        {"valuation_policy_assignments": assignments},
    )
    client.ingest(
        "/ingest/authoritative-market-price-source-facts", {"market_price_source_facts": facts}
    )
    client.ingest(
        "/ingest/business-dates",
        {"business_dates": [{"business_date": day} for day in (FIRST_DAY, LAST_DAY)]},
    )
    if not same_currency:
        client.ingest(
            "/ingest/fx-rates",
            {
                "fx_rates": [
                    {
                        "from_currency": "XTS",
                        "to_currency": "USD",
                        "rate_date": FIRST_DAY,
                        "rate": "2.5",
                    }
                ]
            },
        )
    buy_id = f"FX1158_BUY_{suffix}"
    transaction = {
        "transaction_id": buy_id,
        "portfolio_id": portfolio,
        "instrument_id": equity,
        "security_id": equity,
        "transaction_date": f"{FIRST_DAY}T10:00:00Z",
        "settlement_date": f"{FIRST_DAY}T10:00:00Z",
        "transaction_type": "BUY",
        "quantity": "10",
        "price": "100",
        "gross_transaction_amount": "1000",
        "trade_currency": trade_currency,
        "currency": trade_currency,
        "transaction_fx_rate": booked_fx,
        "cash_entry_mode": "AUTO_GENERATE",
        "settlement_cash_account_id": cash,
        "settlement_cash_instrument_id": cash,
        "source_system": "SYNTHETIC_FX_ACCEPTANCE",
    }
    accepted = client.ingest("/ingest/transactions", {"transactions": [transaction]})
    assert accepted.status_code == 202 and accepted.json()["accepted_count"] == 1
    # Native price events schedule valuation; explicit source facts above supply its policy inputs.
    client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {
                    "security_id": fact["security_id"],
                    "price_date": fact["price_date"],
                    "price": fact["price"],
                    "currency": fact["currency"],
                }
                for fact in facts
            ]
        },
    )
    return {
        "portfolio": portfolio,
        "equity": equity,
        "cash": cash,
        "buy_id": buy_id,
        "transaction": transaction,
        "acceptance": accepted.json(),
    }


def funded_cash_transactions(scenario):
    """Source commands for a positive cash book; admission stays in the owning E2E."""
    source = scenario["transaction"]
    common = {
        "portfolio_id": scenario["portfolio"],
        "trade_currency": source["trade_currency"],
        "currency": source["currency"],
        "transaction_fx_rate": source["transaction_fx_rate"],
        "source_system": "SYNTHETIC_FX_ACCEPTANCE",
    }
    funding = {
        **common,
        "transaction_id": f"{scenario['buy_id']}-FUND",
        "security_id": scenario["cash"],
        "instrument_id": scenario["cash"],
        "transaction_date": f"{FIRST_DAY}T09:00:00Z",
        "settlement_date": f"{FIRST_DAY}T09:00:00Z",
        "transaction_type": "DEPOSIT",
        "quantity": "2000",
        "price": "1",
        "gross_transaction_amount": "2000",
    }
    sale = {
        **source,
        "transaction_id": f"{scenario['buy_id']}-SELL",
        "transaction_date": f"{FIRST_DAY}T16:00:00Z",
        "settlement_date": f"{LAST_DAY}T10:00:00Z",
        "transaction_type": "SELL",
        "quantity": "5",
        "price": "110",
        "gross_transaction_amount": "550",
        "trade_fee": "2",
    }
    fee_buy = {
        **source,
        "transaction_id": f"{scenario['buy_id']}-FEE-BUY",
        "transaction_date": f"{LAST_DAY}T09:00:00Z",
        "settlement_date": f"{LAST_DAY}T09:00:00Z",
        "quantity": "1",
        "gross_transaction_amount": "100",
        "trade_fee": "2",
    }
    income = {
        **source,
        "transaction_id": f"{scenario['buy_id']}-DIVIDEND",
        "transaction_date": f"{FIRST_DAY}T18:00:00Z",
        "settlement_date": f"{LAST_DAY}T12:00:00Z",
        "transaction_type": "DIVIDEND",
        "quantity": "0",
        "price": "0",
        "gross_transaction_amount": "100",
        "trade_fee": "2",
    }
    interest = {
        **income,
        "transaction_id": f"{scenario['buy_id']}-INTEREST",
        "transaction_type": "INTEREST",
        "gross_transaction_amount": "50",
        "net_interest_amount": "50",
        "interest_direction": "INCOME",
        "settlement_date": f"{LAST_DAY}T13:00:00Z",
    }
    return [
        ("funded_buy", funding),
        ("funded_fee_buy", fee_buy),
        ("funded_sell", sale),
        ("funded_income", income),
        ("funded_interest", interest),
    ]
