### **RFC 012: Portfolio Review API**

  * **Status**: **Final** (was: Proposed)
  * **Date**: 2025-08-31
  * **Lead**: Gemini Architect
  * **Services Affected**: `query-service`
  * **Related RFCs**: RFC 007, RFC 008

-----

## 1\. Summary (TL;DR)

This RFC is approved. We will implement a new, consolidated `POST /portfolios/{portfolio_id}/review` endpoint within the `query-service`. This endpoint will act as a server-side orchestrator, generating a comprehensive, multi-section portfolio review report from a single API call.

This approach solves the inefficiency and potential for data inconsistency inherent in client-side aggregation. By performing the orchestration on the backend within a single request scope, we can **guarantee that all sections of the report (Performance, Risk, Allocation, etc.) are calculated against the exact same atomic snapshot of the portfolio's active data version (epoch)**, which is the feature's most critical requirement.

-----

## 2\. Decision

[cite\_start]We will implement a new `ReviewService` within the `query-service`[cite: 2355]. This service will orchestrate calls to existing internal services (`SummaryService`, `PerformanceService`, `RiskService`, etc.) to construct a standardized report. The API will be intentionally simple, accepting only a list of desired sections and returning a pre-configured, non-customizable JSON payload suitable for populating a client-facing report.

-----

## 3\. Architectural Consequences

### **Pros**:

  * **Guaranteed Data Consistency**: This is the most significant benefit. [cite\_start]The `ReviewService` will fetch all underlying data by joining with the `position_state` table to filter for the **current, active `epoch`** for each security[cite: 2222, 2274]. This provides an atomic, point-in-time snapshot, ensuring that performance, risk, and allocation figures are perfectly aligned and free from race conditions with ongoing reprocessing flows.
  * **Client Simplicity**: Shifts orchestration logic from the client to the backend. [cite\_start]A front-end application only needs to make one API call to populate an entire multi-faceted review screen, drastically reducing complexity and the number of network round-trips[cite: 2354].
  * [cite\_start]**Backend Efficiency**: By using `asyncio.gather`, the `ReviewService` can execute data fetching and calculations for all sections in parallel, minimizing overall latency compared to sequential client-side calls[cite: 2356].
  * **Centralized Business Logic**: The server defines what constitutes a "standard" portfolio review (e.g., which performance periods, which risk metrics). This ensures a consistent analytical experience for all users and simplifies client implementations.

### **Cons / Trade-offs**:

  * **Single Point of Failure**: As an aggregator, the `/review` endpoint's success is dependent on the success of all its sub-service calls. A failure in any single component (e.g., `RiskService`) will cause the entire endpoint to fail. This is an acceptable trade-off for the guarantee of data consistency.
  * [cite\_start]**Static Configuration (v1)**: The report structure (e.g., performance periods) is intentionally static for v1 to reduce complexity[cite: 2358]. Future iterations could introduce more configurability if required.

-----

## 4\. High-Level Design

### 4.1. Orchestration within `query-service`

The new `ReviewService` will be the orchestrator. It will **not** contain any new financial logic itself. Instead, it will:

1.  Receive the `PortfolioReviewRequest`.
2.  Instantiate the other required services (`SummaryService`, `PerformanceService`, `RiskService`, etc.).
3.  [cite\_start]Execute all data aggregation and calculation calls concurrently using `asyncio.gather`[cite: 2356].
4.  Assemble the results from each service into the final `PortfolioReviewResponse` DTO.

### 4.2. The Consistency Guarantee

[cite\_start]To ensure atomic consistency, the `ReviewService` and all underlying repository methods it calls will strictly adhere to the system's **Epoch/Watermark** model[cite: 2049]. [cite\_start]Every query that fetches versioned data (e.g., from `daily_position_snapshots`, `portfolio_timeseries`) **must** join with `position_state` and filter on `table.epoch = position_state.epoch`[cite: 2222, 2274]. This correctly fences off any stale data from prior, incomplete reprocessing flows and is the cornerstone of this feature's reliability.

-----

## 5\. API Contract

New DTOs will be defined in `src/services/query_service/app/dtos/review_dto.py`.

### Request Body

```json
{
  "as_of_date": "2025-08-30",
  "sections": [
    "OVERVIEW",
    "ALLOCATION",
    "PERFORMANCE",
    "RISK_ANALYTICS",
    "INCOME_AND_ACTIVITY",
    "HOLDINGS",
    "TRANSACTIONS"
  ]
}
```

### Response Body Structure & Data Sources

  * [cite\_start]**`overview`**: Data from `SummaryService` and `PortfolioService`[cite: 2357].
  * [cite\_start]**`allocation`**: All available breakdowns from `SummaryService`[cite: 2357].
  * [cite\_start]**`performance`**: A static set of periods (MTD, QTD, YTD, 1Y, 3Y, SI) with cumulative and annualized returns (NET & GROSS), plus a 12-month breakdown, generated by `PerformanceService`[cite: 2358].
  * [cite\_start]**`risk_analytics`**: Key metrics for YTD and 3-Year periods, generated by `RiskService`[cite: 2358].
  * [cite\_start]**`income_and_activity`**: YTD summary from `SummaryService`[cite: 2358].
  * [cite\_start]**`holdings`**: Current holdings, grouped by asset class, from `PositionService`[cite: 2358].
  * [cite\_start]**`transactions`**: Recent transactions (YTD), grouped by asset class, from `TransactionService`[cite: 2359].

-----

## 6\. Observability

To monitor this new, high-value endpoint, the following will be implemented:

  * **Metrics**: A new Prometheus `Histogram` named `review_generation_duration_seconds` will be added to the `ReviewService` to track the overall latency of the end-to-end orchestration.
  * **Logging**: The `ReviewService` will emit structured logs at the beginning and end of each request, including the `portfolio_id` and total duration. It will also log the duration of each parallel sub-service call to easily identify bottlenecks. All logs will be tagged with the request's `correlation_id`.

-----

## 7\. Implementation Plan

1.  **Phase 1: DTOs and Scaffolding**:

      * [cite\_start]Create `review_dto.py`, `review_service.py`, and the router in `routers/review.py` within the `query_service`[cite: 2363].
      * Wire the new router into `main.py`.

2.  **Phase 2: Orchestration & Data Aggregation**:

      * [cite\_start]Implement the `asyncio.gather` calls in `ReviewService` to orchestrate the existing services (`SummaryService`, `PerformanceService`, etc.)[cite: 2363].
      * Construct the static, pre-configured request objects required for each sub-service call.

3.  **Phase 3: Response Assembly & Transformation**:

      * [cite\_start]Implement the logic to map the results from the sub-services into the final `PortfolioReviewResponse` DTO[cite: 2363].
      * Implement the server-side grouping logic for holdings and transactions by `asset_class`.

4.  **Phase 4: Observability & Testing**:

      * Add the `review_generation_duration_seconds` Prometheus metric and structured logging.
      * [cite\_start]Add comprehensive unit tests for the `ReviewService`, integration tests for the endpoint, and a new end-to-end test to validate the entire flow and the final, complex JSON payload[cite: 2364].

-----

## 8\. Alternatives Considered

  * **Client-Side Aggregation**: We explicitly rejected this approach. [cite\_start]It would require multiple network calls, making it less efficient and, more importantly, unable to guarantee that all data is fetched from the same atomic data version (epoch), potentially leading to inconsistent reports[cite: 2354].
  * **New `reporting-service`**: Creating a new microservice was deemed unnecessary complexity for this synchronous, on-demand API. The logic is purely orchestration of existing components within the `query-service`, so placing it there is the most performant and architecturally consistent solution. [cite\_start]A separate service would be justified for asynchronous, large-scale batch report generation, but that is not the current requirement[cite: 2356].