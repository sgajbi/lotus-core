#!/bin/bash

# A simple script to run the full E2E dual-currency example flow.
# Ensure the Docker environment is running before executing this script.
# Usage: ./scripts/development/run_e2e_example.sh

set -e # Exit immediately if a command exits with a non-zero status.

BASE_URL="http://localhost:8000"
QUERY_URL="http://localhost:8001"
PORTFOLIO_ID="DUAL_CURRENCY_PORT_01"
SECURITY_ID="SEC_DAI_DE"

echo "---"
echo "🚀 Starting E2E Example Flow..."
echo "---"

echo "STEP 1: Ingesting a USD-based Portfolio..."
curl -s -X 'POST' \
  "${BASE_URL}/ingest/portfolios" \
  -H 'Content-Type: application/json' \
  -d '{
  "portfolios": [{"portfolioId": "'"$PORTFOLIO_ID"'", "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "DC_CIF", "status": "ACTIVE", "riskExposure":"High", "investmentTimeHorizon":"Long", "portfolioType":"Discretionary", "bookingCenter":"SG"}]
}' | head -n 1

echo "\nSTEP 2: Ingesting a EUR-based Instrument (Daimler AG)..."
curl -s -X 'POST' \
  "${BASE_URL}/ingest/instruments" \
  -H 'Content-Type: application/json' \
  -d '{
  "instruments": [{"securityId": "'"$SECURITY_ID"'", "name": "Daimler AG", "isin": "DE0007100000", "instrumentCurrency": "EUR", "productType": "Equity"}]
}' | head -n 1

echo "\nSTEP 3: Ingesting FX Rates..."
curl -s -X 'POST' \
  "${BASE_URL}/ingest/fx-rates" \
  -H 'Content-Type: application/json' \
  -d '{
  "fx_rates": [
    {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": "2025-08-10", "rate": "1.10"},
    {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": "2025-08-15", "rate": "1.20"}
  ]
}' | head -n 1

echo "\nSTEP 4: Ingesting a BUY Transaction (in EUR)..."
curl -s -X 'POST' \
  "${BASE_URL}/ingest/transactions" \
  -H 'Content-Type: application/json' \
  -d '{
  "transactions": [{"transaction_id": "DC_BUY_01", "portfolio_id": "'"$PORTFOLIO_ID"'", "instrument_id": "DAI", "security_id": "'"$SECURITY_ID"'", "transaction_date": "2025-08-10T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 150.0, "gross_transaction_amount": 15000.0, "trade_currency": "EUR", "currency": "EUR"}]
}' | head -n 1

echo "\nSTEP 5: Ingesting a SELL Transaction (in EUR)..."
curl -s -X 'POST' \
  "${BASE_URL}/ingest/transactions" \
  -H 'Content-type: application/json' \
  -d '{
   "transactions": [{"transaction_id": "DC_SELL_01", "portfolio_id": "'"$PORTFOLIO_ID"'", "instrument_id": "DAI", "security_id": "'"$SECURITY_ID"'", "transaction_date": "2025-08-15T10:00:00Z", "transaction_type": "SELL", "quantity": 40, "price": 170, "gross_transaction_amount": 6800, "trade_currency": "EUR", "currency": "EUR"}]
}' | head -n 1

echo "\nSTEP 6: Ingesting a Market Price (in EUR)..."
curl -s -X 'POST' \
  "${BASE_URL}/ingest/market-prices" \
  -H 'Content-Type: application/json' \
  -d '{
  "market_prices": [{"securityId": "'"$SECURITY_ID"'", "priceDate": "2025-08-15", "price": 180.0, "currency": "EUR"}]
}' | head -n 1

echo "\n---"
echo "✅ Ingestion complete. Waiting 10 seconds for events to be processed..."
echo "---"
sleep 10

echo "\nSTEP 7: Querying Final Position..."
echo "Running: curl ${QUERY_URL}/portfolios/${PORTFOLIO_ID}/positions"
curl -s "${QUERY_URL}/portfolios/${PORTFOLIO_ID}/positions" | python -m json.tool

echo "\n---"
echo "\nSTEP 8: Querying Transactions with Realized P&L..."
echo "Running: curl ${QUERY_URL}/portfolios/${PORTFOLIO_ID}/transactions"
curl -s "${QUERY_URL}/portfolios/${PORTFOLIO_ID}/transactions" | python -m json.tool

echo "\n---"
echo "🎉 E2E Example Flow Complete!"
echo "---"