"""Synthetic source-owned inputs admitted only through the registered HTTP APIs."""

import hashlib
import json

from tests.test_support.booked_fx_cash_oracle import FIRST_DAY, LAST_DAY


def seed_scenario(client, suffix):
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
    client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "security_id": security,
                    "name": f"Synthetic {kind}",
                    "isin": security,
                    "currency": "XTS",
                    "product_type": kind,
                    "asset_class": kind,
                }
                for security, kind in ((equity, "Equity"), (cash, "Cash"))
            ]
        },
    )
    for security in (equity, cash):
        client.poll_for_data(
            f"/instruments?security_id={security}",
            lambda body, expected=security: any(
                row["security_id"] == expected for row in body.get("instruments", [])
            ),
        )
    client.ingest(
        "/ingest/reference/cash-accounts",
        {
            "cash_accounts": [
                {
                    "cash_account_id": cash,
                    "portfolio_id": portfolio,
                    "security_id": cash,
                    "display_name": "Synthetic XTS settlement",
                    "account_currency": "XTS",
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
            source = {"security": security, "day": day, "price": price, "currency": "XTS"}
            facts.append(
                {
                    "tenant_id": client.tenant_id,
                    "legal_book_id": book,
                    "security_id": security,
                    "price_date": day,
                    "price": price,
                    "currency": "XTS",
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
    client.ingest(
        "/ingest/fx-rates",
        {
            "fx_rates": [
                {"from_currency": "XTS", "to_currency": "USD", "rate_date": day, "rate": rate}
                for day, rate in ((FIRST_DAY, "2"), (LAST_DAY, "2.5"))
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
        "trade_currency": "XTS",
        "currency": "XTS",
        "transaction_fx_rate": "2",
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
