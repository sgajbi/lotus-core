### **RFC 017: Position-Level Analytics API**

Superseded by RFC 057. The `POST /portfolios/{portfolio_id}/positions-analytics` endpoint is removed from lotus-core, and canonical position-level fields are served via `GET /portfolios/{portfolio_id}/positions`.

  * **Status**: Final
  * **Date**: 2025-08-31
  * **Lead**: Gemini Architect
  * **Services Affected**: `query-service`, `portfolio-common`
  * **Related RFCs**: RFC 007, RFC 008, RFC 012

-----

## 1\. Summary (TL;DR)

This RFC approves the creation of a new, configurable endpoint, **`POST /portfolios/{portfolio_id}/positions-analytics`**, within the `query-service`. This endpoint will provide a comprehensive, on-the-fly analytical view of each individual position within a portfolio, addressing a critical gap in our current analytics capabilities.

The new feature will enrich each position with key metrics, including **performance (TWR), total income, held since date, and portfolio weight**, along with a full set of instrument reference data. All analytics will be calculated in both the instrument's local currency and the portfolio's base currency. The design reuses the existing `performance-calculator-engine`, adheres to the system's **epoch-aware** data consistency model to guarantee correctness, and follows the established architectural pattern of stateless, on-demand calculations.

-----

## 2\. Architectural Consequences

### **Pros**:

  * **Guaranteed Data Consistency**: This is the most significant benefit. The service will fetch all underlying data by joining with the `position_state` table to filter for the **current, active `epoch`** for each security. This provides an atomic, point-in-time snapshot, ensuring that position-level performance, income, and valuation figures are perfectly aligned with portfolio-level reports like the `/review` and `/summary` endpoints.
  * **Client Simplicity & Efficiency**: Aggregates all necessary position-level data into a single, configurable API call. This drastically reduces network overhead and streamlines front-end development by removing the need for client-side orchestration.
  * **Backend Efficiency**: By fetching a base set of positions once and then executing analytical enrichments concurrently using `asyncio.gather`, the service minimizes latency. This mirrors the efficient orchestration pattern proven in the `ReviewService` (RFC 012).
  * **High Reusability**: The design makes extensive reuse of existing, well-tested components, particularly the `performance-calculator-engine` for all TWR calculations, which reduces implementation risk and ensures methodological consistency.

### **Cons / Trade-offs**:

  * **Potential for High Latency**: For portfolios with a very large number of positions (e.g., \>1000), calculating performance for every single holding on-the-fly could lead to slower response times. This is an acceptable trade-off for the guarantee of data freshness and consistency. Future optimizations could include pagination or a more targeted selection of positions if this becomes a production issue.

-----

## 3\. High-Level Design

The implementation will be logically contained within the `query-service` and will follow patterns established by the existing on-the-fly analytics endpoints (`/risk`, `/summary`, `/review`).

### 3.1. New API Endpoint

A new endpoint will be created: **`POST /portfolios/{portfolio_id}/positions-analytics`**.

The `POST` method is used to allow for a rich, JSON-based request body. This provides maximum flexibility for clients to request only the specific analytical sections they need, which is more scalable than using a large number of query parameters.

### 3.2. New `PositionAnalyticsService`

A new `PositionAnalyticsService` will be created within `src/services/query_service/app/services/`. This service will act as the primary orchestrator and will be responsible for:

1.  Parsing the incoming `PositionAnalyticsRequest`.
2.  Fetching the base position data for the portfolio using the `PositionRepository`.
3.  For each position, concurrently executing the required analytical enrichment tasks (e.g., performance calculation, income summation) using `asyncio.gather`.
4.  Assembling the final, enriched `PositionAnalyticsResponse`.

### 3.3. The Consistency Guarantee (Epoch-Awareness)

This feature's reliability hinges on strict adherence to the system's epoch/watermark model. All underlying repository methods used by the `PositionAnalyticsService` **must** be epoch-aware. Every query for historical or stateful data (from `daily_position_snapshots`, `position_history`, `position_timeseries`, `cashflows`, etc.) will join with the `position_state` table and filter on `table.epoch = position_state.epoch` for the given key. This guarantees that all calculations are performed on an atomically consistent and complete version of the data, preventing corruption from in-progress reprocessing flows.

-----

## 4\. Detailed Calculation Methodologies

The calculation strategies are approved as outlined in the draft.

| Metric | Primary Data Source(s) | Calculation Strategy |
| :--- | :--- | :--- |
| **Base Position & Valuation** | `daily_position_snapshots`, `instruments` | We will extend the existing `PositionRepository.get_latest_positions_by_portfolio` method to fetch all required instrument reference data in a single, efficient query. This provides the core data: quantity, market value (local and base), and cost basis (local and base). Unrealized P\&L is derived from these values. |
| **`held_since_date`** | `position_history` | This date will be derived dynamically. We will query for the most recent date *before* the current holding period where the position quantity was zero. The `held_since_date` will be the date of the subsequent transaction that re-opened the position. If no such zero-quantity point exists, the date of the very first transaction will be used. |
| **`total_income`** | `cashflows`, `fx_rates` | We will sum all records from the `cashflows` table where the `classification` is `INCOME` for the specific position since its `held_since_date`. The calculation will first be performed in the instrument's local currency. A second calculation will convert each cashflow amount to the portfolio's base currency using the FX rate from the respective `cashflow_date`. |
| **`weight`** | `daily_position_snapshots` | Calculated as `position.market_value_base / portfolio_total_market_value_base`. The portfolio's total market value is the sum of `market_value_base` across all positions fetched in the initial step. |
| **Performance (TWR)** | `position_timeseries`, `fx_rates` | We will reuse the `performance-calculator-engine`. For each position and requested period: \<br\> 1. Fetch the corresponding data from the `position_timeseries` table. \<br\> 2. Instantiate `PerformanceCalculator` and calculate the return. This yields the performance in the **local currency**. \<br\> 3. To get the **base currency** return, we will fetch the daily FX rates for the period, apply them to the daily return series, and run the calculation a second time. This correctly captures the P\&L contribution from FX movements. |

-----

## 5\. API Schema Definition

The API schema is approved as defined in the draft. A new DTO file will be created at `src/services/query_service/app/dtos/position_analytics_dto.py`.

#### **Request: `POST /portfolios/{portfolio_id}/positions-analytics`**

```json
{
  "as_of_date": "2025-08-31",
  "sections": [
    "BASE",
    "INSTRUMENT_DETAILS",
    "VALUATION",
    "INCOME",
    "PERFORMANCE"
  ],
  "performanceOptions": {
    "periods": ["MTD", "QTD", "YTD", "ONE_YEAR", "SI"]
  }
}
```

#### **Response Body**

```json
{
  "portfolioId": "E2E_REVIEW_01",
  "as_of_date": "2025-08-31",
  "totalMarketValue": 101270.00,
  "positions": [
    {
      "securityId": "SEC_AAPL",
      "quantity": 100.0,
      "weight": 0.158,
      "heldSinceDate": "2025-08-20",
      
      "instrumentDetails": {
        "name": "Apple Inc.",
        "isin": "US_AAPL_REVIEW",
        "assetClass": "Equity",
        "sector": "Technology",
        "countryOfRisk": "US",
        "currency": "USD"
      },

      "valuation": {
        "marketValue": {
          "local": {"amount": 16000.00, "currency": "USD"},
          "base": {"amount": 16000.00, "currency": "USD"}
        },
        "costBasis": {
          "local": {"amount": 15000.00, "currency": "USD"},
          "base": {"amount": 15000.00, "currency": "USD"}
        },
        "unrealizedPnl": {
          "local": {"amount": 1000.00, "currency": "USD"},
          "base": {"amount": 1000.00, "currency": "USD"}
        }
      },

      "income": {
        "local": {"amount": 120.00, "currency": "USD"},
        "base": {"amount": 120.00, "currency": "USD"}
      },

      "performance": {
        "YTD": {
          "localReturn": 12.80,
          "baseReturn": 12.80
        }
      }
    }
  ]
}
```

-----

## 6\. Implementation Plan

1.  **Phase 1: DTOs & Scaffolding**:
      * Create `position_analytics_dto.py` in `query_service/app/dtos/` with all Pydantic request and response models.
      * Create the skeleton for `PositionAnalyticsService` in `query_service/app/services/`.
      * Create the new router in `query_service/app/routers/` and register the `POST /portfolios/{portfolio_id}/positions-analytics` endpoint in `main.py`.
2.  **Phase 2: Core Logic & Repository Enhancements**:
      * Extend `PositionRepository` and other required repositories with the necessary epoch-aware data-fetching methods.
      * Implement the calculation logic for non-performance metrics (`held_since_date`, `total_income`, `weight`) within the `PositionAnalyticsService`.
      * Integrate the `performance-calculator-engine` to handle the position-level TWR calculations, including the dual-currency logic.
3.  **Phase 3: Orchestration & Observability**:
      * Implement the `asyncio.gather` orchestration within the `PositionAnalyticsService` to run enrichment tasks concurrently.
      * Add the `position_analytics_duration_seconds` and `position_analytics_section_requested_total` Prometheus metrics and structured logging.
4.  **Phase 4: Testing**:
      * Add comprehensive unit tests for all new calculation logic.
      * Add integration tests for the repository methods and the API endpoint contract.
      * Create a new end-to-end test that ingests a multi-currency portfolio and verifies the final API response against expected values.

-----

## 7\. Alternatives Considered

  * **Client-Side Aggregation**: This was rejected as it would require the front end to make multiple API calls (e.g., to `/positions`, `/performance`, `/cashflows` for each position), which is inefficient and cannot guarantee the atomic data consistency that our epoch-aware backend orchestration provides.
  * **Pre-calculating and Storing Metrics**: This was rejected as it violates our architectural principle of performing analytics on-the-fly. Pre-calculation would introduce data staleness and significant complexity around cache invalidation during reprocessing flows.

-----

## 8\. Acceptance Criteria

1.  A new `POST /portfolios/{portfolio_id}/positions-analytics` endpoint exists in the `query_service`.
2.  The API response is configurable via the `sections` array in the request body.
3.  All calculations are verifiably epoch-aware and consistent with other system analytics.
4.  All monetary values (market value, cost basis, P\&L, income) and performance returns are correctly calculated and returned in both local and portfolio base currencies.
5.  The `performance-calculator-engine` is reused for position-level TWR calculations.
6.  The new feature is covered by comprehensive unit, integration, and end-to-end tests.
7.  New Prometheus metrics for latency and feature usage are implemented.
