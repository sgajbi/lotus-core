
# Data Flow Guide: Core Data Ingestion

This document outlines the internal data flow that occurs when a client interacts with the `ingestion_service`.

## 1. Process Overview

The ingestion process is designed to be simple, fast, and asynchronous. The `ingestion_service` acts as a lightweight gateway. Its sole purpose is to validate incoming data and publish it to the correct Kafka topic. All complex business logic and database persistence are handled by downstream consumers.

### Step-by-Step Flow for a Transaction

1.  **API Request:** A client sends a `POST /ingest/transactions` request with a JSON payload containing one or more transactions.
2.  **Correlation ID:** The FastAPI middleware checks for an `X-Correlation-ID` header. If one is not present, it generates a new one (e.g., `ING:uuid`). This ID is logged with every message related to this request.
3.  **Validation:** The endpoint's Pydantic model (`TransactionIngestionRequest`) parses and validates the request body. If validation fails (e.g., missing fields, incorrect data types), the service immediately returns a `422 Unprocessable Entity` error.
4.  **Publishing:** For each valid transaction in the payload, the `IngestionService` calls the shared `KafkaProducer`.
5.  **Kafka Message:** A message is produced to the designated Kafka topic. Crucially, the message is **keyed by the `portfolio_id`**. This ensures that all messages for a given portfolio are sent to the same Kafka partition, which guarantees they will be processed sequentially by downstream consumers.
6.  **Response:** Once all messages have been handed off to the producer's buffer, the service immediately returns a `202 Accepted` response to the client. It does not wait for the messages to be physically written to Kafka.

## 2. Endpoint-to-Topic Mapping

The service routes data from each API endpoint to a specific Kafka topic with a defined keying strategy.

| API Endpoint | Kafka Topic | Kafka Message Key | Purpose of Key |
| :--- | :--- | :--- | :--- |
| `/ingest/portfolios` | `portfolios.raw.received` | `portfolioId` | Group all events for a portfolio. |
| `/ingest/instruments` | `instruments.received` | `securityId` | Group all events for an instrument. |
| `/ingest/transactions` | `transactions.raw.received` | `portfolio_id` | **Sequential processing** for a portfolio's activity. |
| `/ingest/market-prices` | `market_prices.raw.received` | `securityId` | Group all prices for an instrument. |
| `/ingest/fx-rates` | `fx_rates.raw.received` | `from-to` (e.g., EUR-USD) | Group all rates for a currency pair. |
| `/ingest/business-dates` | `business_dates.raw.received` | `businessDate` | Group events for a specific day. |
| `/reprocess/transactions` | `transactions.reprocessing.requested` | `transaction_id` | Target a specific transaction for reprocessing. |

## 3. Design Considerations

* **Schema Enforcement:** Validation currently occurs at the API edge via Pydantic. The system does not use a central schema registry (like Confluent Schema Registry) to enforce schemas on the Kafka topics themselves. This means consumers trust that all producers for a given topic adhere to the `portfolio-common/events.py` contract.
