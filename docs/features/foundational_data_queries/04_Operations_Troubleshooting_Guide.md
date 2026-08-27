# Operations & Troubleshooting Guide: Foundational Data Queries

This guide provides operational and troubleshooting instructions for the foundational data query endpoints.

## 1. Troubleshooting Principles

The foundational `GET` endpoints are a read-through layer for data that has already been processed and persisted by the upstream pipeline. Therefore, issues with these endpoints almost always point to a problem in an upstream service.

* **Symptom:** Data is missing or incorrect when a user calls a `GET` endpoint (e.g., a transaction is missing from the `/transactions` response).
* **Diagnosis:** The issue is **not** in the `query_service`. The `query_service` is correctly showing that the data does not exist in the final database tables.
* **Resolution:** The problem lies in the data pipeline that populates those tables.
    1.  Trace the data point back to the `ingestion_service` using the `correlation_id` to confirm it was received.
    2.  Check the logs of the relevant consumer service (`persistence_service`, `portfolio_transaction_processing_service`, etc.) for errors related to that `correlation_id`. The data was likely either dropped in a Dead-Letter Queue (DLQ) or is stuck in a retry loop.