# RFC 027: Enhance Performance of Position-Level Analytics

Superseded by RFC 057. `positions-analytics` has been retired from lotus-core; position-level contract evolution continues on canonical `GET /portfolios/{portfolio_id}/positions`.

* **Status**: Proposed
* **Date**: 2025-09-01
* **Related RFCs**: RFC 017

## 1. Summary

The `POST /positions-analytics` endpoint provides critical, detailed insights but faces a significant performance and scalability challenge. The current on-the-fly TWR calculation for every position in a portfolio can lead to high API latency and heavy database load, especially for large portfolios or long date ranges.

This RFC proposes a phased approach to address this:
1.  **Short-term:** Implement a service-level cache to handle repeated requests efficiently.
2.  **Long-term:** Introduce a pre-calculation and persistence layer for common performance metrics to drastically improve response times for the most frequent queries.

## 2. The Problem: On-the-Fly Calculation at Scale

The current design prioritizes data freshness by calculating everything at request time. While correct, this has a high cost: a request for a 500-position portfolio with 5 performance periods (e.g., MTD, YTD, 1Y, 3Y, SI) could trigger thousands of database queries and 2,500 individual TWR calculations in a single API call. This will not scale and risks creating a poor user experience or even service timeouts.

## 3. Proposed Solutions

### 3.1. Phase 1: Service-Level Caching (Tactical)

* **Proposal:** We will introduce a short-lived, in-memory cache (e.g., using `cachetools` or a similar library) within the `PositionAnalyticsService`.
    * The cache key will be a hash of the `portfolio_id`, `as_of_date`, and the requested `sections`.
    * The final `PositionAnalyticsResponse` object will be cached for a short duration (e.g., 5-15 minutes).
* **Benefit:** This provides an immediate performance boost for repeated requests, such as a user refreshing a page or multiple users viewing the same portfolio around the same time, without requiring major architectural changes.
* **Limitation:** The first request is still slow, and the cache offers no benefit for ad-hoc queries. Cache invalidation is complex due to the reprocessing engine, so a simple time-to-live (TTL) is the only safe initial approach.

### 3.2. Phase 2: Pre-calculation of Standard Metrics (Strategic)

* **Proposal:** For a robust, long-term solution, we will pre-calculate and persist the most common position-level performance metrics.
    1.  **New Table (`position_analytics_cache`):** A new database table will be created to store pre-calculated results.
        | Column | Type | Description |
        | :--- | :--- | :--- |
        | `portfolio_id` | `VARCHAR` (PK) | |
        | `security_id` | `VARCHAR` (PK) | |
        | `date` | `DATE` (PK) | The "as of" date for the analytics. |
        | `epoch` | `INTEGER` | The epoch of the data used for the calculation. |
        | `twr_ytd` | `NUMERIC` | The calculated Year-to-Date TWR. |
        | `twr_1y` | `NUMERIC` | The calculated 1-Year TWR. |
        | `...other_metrics`| | Other common metrics (MTD, QTD, SI). |
    2.  **New Background Service:** A new, dedicated microservice (`analytics-precalculation-service`) will be created. It will subscribe to the `portfolio_timeseries_generated` Kafka topic. When a new time-series record is created for a given day, this service will trigger the calculation for all standard performance periods for all positions in that portfolio and save the results to the new table.
    3.  **API Logic Change:** The `PositionAnalyticsService` will be refactored. When a request for a standard period (like YTD) is received, it will first attempt to fetch the result from the `position_analytics_cache` table. If a result is found for the correct epoch, it will be returned instantly. It will only fall back to the on-the-fly calculation for custom date ranges or if the pre-calculated value is missing.

* **Benefit:** This provides a massive performance improvement for the most common user workflows, making the application feel instantaneous while still allowing for the flexibility of on-demand calculations for ad-hoc requests.
