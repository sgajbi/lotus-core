# API Specification: Core Data Ingestion

This document provides the detailed technical specification for the `ingestion_service` API.

* **Base URL:** `http://core-ingestion.dev.lotus`
* **Success Response:** All endpoints return a `202 Accepted` status code upon successfully queueing the data for processing.
* **Error Responses:**
    * `409 Conflict`: The idempotency key conflicts with another payload, or the matching request
      remains in a non-replay-safe `accepted` state.
    * `422 Unprocessable Entity`: The request body is malformed or fails validation.
    * `500 Internal Server Error`: An unexpected server-side error occurred.
    * `503 Service Unavailable`: A dependency such as Kafka prevented asynchronous acceptance.
* **Headers:** Every response includes an `X-Correlation-ID` header for end-to-end request tracing.

---

## Idempotent replay outcomes

Job-backed ingestion commands resolve retries from durable lifecycle evidence:

| Existing job evidence | Retry outcome |
| :--- | :--- |
| `queued` with no recorded failure outcome | `202 Accepted`, same job identifier, no repeated work |
| durable failure outcome | original HTTP status, stable code, safe detail, job identifier, and safe response headers |
| `accepted` with no durable outcome | `409 INGESTION_REQUEST_IN_PROGRESS` |
| unknown or incomplete legacy state | fail-closed `500`, never a successful acknowledgement |
| same endpoint and key with a different canonical payload | `409 INGESTION_IDEMPOTENCY_CONFLICT` |

The single-transaction endpoint does not create an ingestion job and therefore does not offer this
job-backed replay contract. A `202` response certifies queue acceptance only; downstream
calculation and persistence remain asynchronous.

---

## 1. Portfolios

* **Method:** `POST`
* **Path:** `/ingest/portfolios`
* **Description:** Ingests a list of portfolios.

#### Request Body

A JSON object containing a `portfolios` key, which holds a list of portfolio objects.

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `portfolioId` | string | Yes | The unique identifier for the portfolio. |
| `baseCurrency` | string | Yes | The portfolio's base reporting currency. |
| `openDate` | string | Yes | The date the portfolio was opened (`YYYY-MM-DD`). |
| `cifId` | string | Yes | The client information file (CIF) identifier. |
| `status` | string | Yes | The current status of the portfolio (e.g., "Active"). |
| `riskExposure` | string | Yes | The client's defined risk profile. |
| `investmentTimeHorizon` | string | Yes | The client's investment time horizon. |
| `portfolioType` | string | Yes | The type of portfolio (e.g., "Discretionary"). |
| `bookingCenter` | string | Yes | The booking center or legal entity. |

#### Example Request

```json
{
  "portfolios": [
    {
      "portfolioId": "PORT_001",
      "baseCurrency": "USD",
      "openDate": "2024-01-01",
      "riskExposure": "Medium",
      "investmentTimeHorizon": "Long",
      "portfolioType": "Discretionary",
      "bookingCenter": "Singapore",
      "cifId": "CIF_12345",
      "status": "Active"
    }
  ]
}
````

-----

## 2\. Instruments

  * **Method:** `POST`
  * **Path:** `/ingest/instruments`
  * **Description:** Ingests a list of financial instruments.

#### Request Body

A JSON object containing an `instruments` key, which holds a list of instrument objects.

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `securityId` | string | Yes | Unique system-wide identifier for the security. |
| `name` | string | Yes | Full name of the instrument. |
| `isin` | string | Yes | International Securities Identification Number. |
| `instrumentCurrency` | string | Yes | The currency the instrument is denominated in. |
| `productType` | string | Yes | Type of product (e.g., "Equity", "Bond"). |
| `assetClass` | string | No | High-level analytical category (e.g., "Fixed Income"). |
| `sector` | string | No | Industry sector for equities (e.g., "Technology"). |
| `issuerId` | string | No | Identifier for the direct issuer of the security. |
| `ultimateParentIssuerId` | string | No | Identifier for the ultimate parent of the issuer. |

#### Example Request

```json
{
  "instruments": [
    {
      "securityId": "SEC_AAPL",
      "name": "Apple Inc.",
      "isin": "US0378331005",
      "instrumentCurrency": "USD",
      "productType": "Equity",
      "assetClass": "Equity",
      "sector": "Technology"
    }
  ]
}
```

-----

## 3\. Transactions

  * **Method:** `POST`
  * **Path:** `/ingest/transactions`
  * **Description:** Ingests a list of financial transactions.

#### Request Body

A JSON object containing a `transactions` key, which holds a list of transaction objects.

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `transaction_id` | string | Yes | Unique identifier for the transaction. |
| `portfolio_id` | string | Yes | The portfolio this transaction belongs to. |
| `security_id` | string | Yes | The security identifier for the instrument traded. |
| `transaction_date` | string | Yes | The date and time of the trade (`YYYY-MM-DDTHH:MM:SSZ`). |
| `transaction_type` | string | Yes | Type of transaction (e.g., "BUY", "SELL", "DIVIDEND"). |
| `quantity` | number | Yes | Quantity of the instrument traded. |
| `price` | number | Yes | Price per unit of the instrument. |
| `gross_transaction_amount` | number | Yes | Non-negative gross economic amount before fees, taxes, or deductions. It must be greater than zero for ordinary transaction families; a governed zero-price redemption may carry truthful zero gross proceeds. |
| `trade_currency` | string | Yes | Currency of the trade. |
| `currency` | string | Yes | Currency of the transaction amounts. |
| `trade_fee` | number | No | Any fees associated with the trade. |

#### Example Request

```json
{
  "transactions": [
    {
      "transaction_id": "TXN_001",
      "portfolio_id": "PORT_001",
      "instrument_id": "AAPL",
      "security_id": "SEC_AAPL",
      "transaction_date": "2025-08-15T10:00:00Z",
      "transaction_type": "BUY",
      "quantity": 10.0,
      "price": 150.0,
      "gross_transaction_amount": 1500.0,
      "trade_currency": "USD",
      "currency": "USD",
      "trade_fee": 5.0
    }
  ]
}
```

-----

## 4\. Market Prices

  * **Method:** `POST`
  * **Path:** `/ingest/market-prices`
  * **Description:** Ingests a list of end-of-day market prices.

#### Example Request

```json
{
  "market_prices": [
    {
      "securityId": "SEC_AAPL",
      "priceDate": "2025-08-15",
      "price": 152.50,
      "currency": "USD"
    }
  ]
}
```

-----

## 5\. FX Rates

  * **Method:** `POST`
  * **Path:** `/ingest/fx-rates`
  * **Description:** Ingests a list of foreign exchange rates.

#### Example Request

```json
{
  "fx_rates": [
    {
      "fromCurrency": "EUR",
      "toCurrency": "USD",
      "rateDate": "2025-08-15",
      "rate": 1.12
    }
  ]
}
```

-----

## 6\. Business Dates

  * **Method:** `POST`
  * **Path:** `/ingest/business-dates`
  * **Description:** Ingests a list of valid business dates, which are used to trigger daily valuation and aggregation processes.

#### Example Request

```json
{
  "business_dates": [
    {
      "businessDate": "2025-08-15"
    }
  ]
}
```

-----

## 7\. Reprocessing Trigger

  * **Method:** `POST`
  * **Path:** `/reprocess/transactions`
  * **Description:** Triggers a reprocessing flow for a list of specific transaction IDs. Each target must resolve through the admitted tenant to a canonical portfolio before job creation or publication. Missing and foreign-tenant transaction IDs return the same not-found response and cause no repair side effect. This is an operational command rather than a data ingestion endpoint.

#### Example Request

```json
{
  "transaction_ids": [
    "TXN_001",
    "TXN_002"
  ]
}
```

 
