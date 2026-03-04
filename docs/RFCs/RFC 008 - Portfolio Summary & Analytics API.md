
### RFC 008: Portfolio Summary & Analytics API (Revised)

  * **Status**: Proposed
  * **Date**: 2025-08-30
  * **Services Affected**: `query-service`, `ingestion_service`, `persistence_service`, `portfolio-common`, `position-calculator`, `cost-calculator-service`

-----

## 1\. Summary (TL;DR)

This RFC proposes the creation of a new, consolidated `POST /portfolios/{portfolio_id}/summary` endpoint in the `query-service`. This endpoint will provide a holistic, dashboard-style view of a portfolio's state as of a given date, designed to be highly efficient for front-end applications.

The summary will include:

  * **Total Wealth & Total Cash**
  * **Contribution & P\&L Summary** (Net New Money, Realized P\&L, Unrealized P\&L Change)
  * **Income & Activity Summaries** (Dividends, Interest, Fees, etc.)
  * **Asset Allocation**

A core prerequisite for the Asset Allocation feature is the enrichment of the `Instrument` data model. This RFC includes a plan to add several new **optional** fields (`assetClass`, `sector`, `country_of_risk`, etc.) to the `instruments` table, along with the necessary updates to the ingestion and persistence pipelines.

-----

## 2\. Motivation

Client advisors and portfolio managers require a single, at-a-glance dashboard view to quickly assess a portfolio's overall status. Currently, retrieving this information would require multiple, separate API calls to different endpoints, which is inefficient for both the client and the backend.

By creating a single, powerful `/summary` endpoint, we can:

  * **Improve Client Efficiency**: Allow a UI to fetch all necessary data for a dashboard in a single network request.
  * **Optimize Backend Performance**: Design the service to fetch underlying data from the database once and compute all summary metrics from that single dataset, avoiding the overhead of multiple round-trips.
  * **Enhance Analytical Capabilities**: The enrichment of the `Instrument` model is a foundational improvement that unlocks sophisticated, multi-dimensional asset allocation analysis, a critical feature for any portfolio management system.

-----

## 3\. Proposed Changes

### 3.1. Prerequisite: Instrument Model Enrichment

To enable multi-dimensional asset allocation, the `instruments` table schema must be updated. All new fields will be **optional (`nullable=True`)** to ensure full backward compatibility with existing data and ingestion flows. The source of this data is assumed to be an external security master provider, delivered via the `ingestion_service`.

**New Fields for `instruments` Table:**

| New Field | Data Type | Description |
| :--- | :--- | :--- |
| `assetClass` | `VARCHAR` | High-level, standardized category (e.g., 'Equity', 'Fixed Income', 'Cash', 'Alternative'). This will be the primary field for analytical classification. |
| `sector` | `VARCHAR` | Industry sector for equities (e.g., 'Technology', 'Healthcare'). |
| `country_of_risk` | `VARCHAR` | The country associated with the instrument's primary risk exposure. |
| `rating` | `VARCHAR` | Credit rating for fixed income instruments (e.g., 'AAA', 'BB+'). |
| `maturity_date` | `DATE` | Maturity date for fixed income instruments. |

This change will require:

1.  An **Alembic migration** to alter the `instruments` table.
2.  Updates to the `InstrumentEvent` in `portfolio-common` and the `Instrument` DTO in `ingestion_service` to accept these new optional fields.
3.  Updates to the `InstrumentConsumer` and `InstrumentRepository` in `persistence_service` to save the new fields to the database.

### 3.2. New API Endpoint: `POST /portfolios/{portfolio_id}/summary`

A single endpoint will accept a request specifying the desired summary sections and calculation parameters. `POST` is used to accommodate the complex request body.

**Request Body (`SummaryRequest`):**

```json
{
  "as_of_date": "2025-08-29",
  "period": {
    "type": "YTD"
  },
  "sections": [
    "WEALTH",
    "ALLOCATION",
    "PNL",
    "INCOME",
    "ACTIVITY"
  ],
  "allocation_dimensions": [
    "ASSET_CLASS",
    "CURRENCY",
    "SECTOR",
    "COUNTRY_OF_RISK",
    "MATURITY_BUCKET"
  ]
}
```

**Response Body (`SummaryResponse`):**

The response will be a JSON object where each requested section is a key.

```json
{
  "scope": {
    "portfolio_id": "...",
    "as_of_date": "...",
    "period_start_date": "...",
    "period_end_date": "..."
  },
  "wealth": {
    "total_market_value": 1250000.50,
    "total_cash": 50000.25
  },
  "pnl_summary": {
    "net_new_money": 10000.00,
    "realized_pnl": 5230.10,
    "unrealized_pnl_change": 12345.67,
    "total_pnl": 17575.77
  },
  "income_summary": {
    "total_dividends": 850.00,
    "total_interest": 120.50
  },
  "activity_summary": {
    "total_inflows": 15000.00,
    "total_outflows": -5000.00,
    "total_fees": -75.50
  },
  "allocation": {
    "by_asset_class": [
      { "group": "Equity", "market_value": 900000.00, "weight": 0.72 },
      { "group": "Fixed Income", "market_value": 300000.25, "weight": 0.24 },
      { "group": "Unclassified", "market_value": 50000.25, "weight": 0.04 }
    ],
    "by_sector": [
        // ...
    ]
  }
}
```

### 3.3. New Service Logic (`SummaryService`)

A new `SummaryService` in the `query_service` will orchestrate all calculations. **Crucially, all queries for historical, versioned data (`daily_position_snapshots`, `cashflows`) must be filtered by the current, active `epoch` for each `(portfolio_id, security_id)` key by joining with the `position_state` table.**

  * **Data Fetching**: The service will instantiate a new `SummaryRepository` to execute a minimal number of optimized queries to fetch all required data from `daily_position_snapshots`, `instruments`, `transactions`, and `cashflows` for the requested portfolio, `as_of_date`, and period.

  * **Wealth & Cash**: Calculated by summing the `market_value` from the single latest `daily_position_snapshot` for each security held on or before the `as_of_date`, filtered for the current `epoch`. Total Cash will be further filtered by `instrument.product_type = 'Cash'`.

  * **P\&L, Income, Activity**: Aggregations based on `transactions` and `cashflows` tables for the specified period, filtered by the current `epoch`.

  * **Asset Allocation**: The service will calculate breakdowns by joining the latest `daily_position_snapshots` (for market values, filtered by `epoch` and `as_of_date`) with the enriched `instruments` table. Any instrument with a `NULL` value for a requested dimension will be grouped into an **"Unclassified"** category.

### 3.4. Refinement: Transaction & Calculation Logic

To ensure data integrity across the system, the following logic for handling specific transaction types must be standardized across all relevant services.

  * **`position-calculator` (`position_logic.py`)**:

      * **`TRANSFER_IN` & `DEPOSIT`**: Must increase position `quantity` by the transaction's `quantity` field and increase `cost_basis` by the `gross_transaction_amount`. Using `gross_transaction_amount` for both is incorrect and must be fixed.
      * **`TRANSFER_OUT` & `WITHDRAWAL`**: Must decrease position `quantity` by the transaction's `quantity` field. The `cost_basis` must be reduced by the proportional FIFO cost of the shares being removed, not by the `gross_transaction_amount`.

  * **`cost-calculator-service` (`cost_calculator.py`)**:

      * **`TRANSFER_IN` & `DEPOSIT`**: Must be handled by a strategy that creates a new cost lot in the disposition engine, similar to a `BUY`. The current fallback to `DefaultStrategy` is incorrect.
      * **`TRANSFER_OUT` & `WITHDRAWAL`**: Must be handled by a strategy that consumes cost lots from the disposition engine, similar to a `SELL`, but must **not** generate a `realized_gain_loss`. The current fallback to `DefaultStrategy` is incorrect.

  * **`query_service` (`summary_service.py`)**:

      * **`MATURITY_BUCKET` Calculation**: The logic must calculate time to maturity relative to the request's `as_of_date`, not `date.today()`.

-----

## 4\. Non-Goals

  * This endpoint will not calculate performance metrics (TWR, MWR). These will remain in the dedicated `/performance` endpoints.
  * This endpoint will not provide a time-series of summary snapshots. It is a point-in-time view as of the requested date.

-----

## 5\. High-Level Implementation Plan

1.  **Phase 1: Instrument Model Enrichment (Foundation)**

      * **DB Migration**: Create and apply an Alembic migration to add the new optional fields to the `instruments` table.
      * **DTOs & Events**: Update `Instrument` DTO (`ingestion_service`) and `InstrumentEvent` (`portfolio-common`) to include the new optional fields.
      * **Persistence**: Update `InstrumentConsumer` (`persistence_service`) to handle and persist the new optional fields.
      * **Testing**: Add unit tests to verify the updated ingestion and persistence logic.

2.  **Phase 2: Summary API Implementation (Feature)**

      * **DTOs**: Create all necessary request/response DTOs for the `/summary` endpoint in a new `dtos/summary_dto.py` file in `query_service`.
      * **Repository**: Create a new `SummaryRepository` in `query_service` to encapsulate the complex, optimized queries required for the summary calculations.
      * **Service**: Implement the new `SummaryService` containing the core business logic, ensuring all data access is filtered by the correct `epoch`.
      * **Router**: Create a new `routers/summary.py` and register the `POST /portfolios/{portfolio_id}/summary` endpoint.
      * **Testing**: Add comprehensive unit and integration tests for the new service and endpoint.

3.  **Phase 3: Documentation & E2E Testing**

      * **E2E Test**: Create a new end-to-end test that ingests an instrument with all new fields and verifies the `/summary` API response, including an "Unclassified" bucket.
      * **Documentation**: Update `README.md` to document the new `/summary` API endpoint.

-----

## 6\. Risks & Mitigation

  * **Performance Risk**: The underlying database query will be complex, joining several large tables.
      * **Mitigation**: The query will be carefully optimized. The query plan will be analyzed using `EXPLAIN ANALYZE`, and new covering indexes will be added to `daily_position_snapshots` and `cashflows` as needed to support efficient lookups by date and epoch.
  * **Data Quality Risk**: The utility of the allocation feature is dependent on the completeness of the new instrument fields.
      * **Mitigation**: The "Unclassified" bucket provides a clear fallback. We will add Prometheus metrics to monitor the percentage of portfolio market value falling into this bucket, creating a data quality KPI.

-----

## 7\. Acceptance Criteria

  * The `instruments` table in the database contains the new optional columns (`assetClass`, `sector`, etc.).
  * The `ingestion_service` can successfully receive and publish an instrument payload containing the new fields.
  * The `persistence_service` successfully saves these new fields.
  * A `POST` request to the new `/portfolios/{portfolio_id}/summary` endpoint returns a `200 OK` with a correctly calculated payload, respecting the current `epoch` for all versioned data.
  * An allocation breakdown requested for a dimension where some instruments have `NULL` values returns an "Unclassified" group.
  * All new logic is covered by unit, integration, and at least one end-to-end test.