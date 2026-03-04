### RFC 016: Concentration Analytics Engine

  * **Status**: **Final**
  * **Date**: 2025-08-31
  * **Services Affected**: `query-service`, New `concentration-analytics-engine` library
  * **Related RFCs**: RFC 007, RFC 008, RFC 012

-----

## 1\. Summary (TL;DR)

This RFC is approved. We will create a new, on-the-fly **Concentration Analytics Engine** to provide insights into portfolio risks not captured by standard volatility metrics. The engine will be implemented as a new, self-contained library (`concentration-analytics-engine`) and exposed via a new, consolidated endpoint in the `query-service`: `POST /portfolios/{portfolio_id}/concentration`.

For v1, it will calculate **Issuer Concentration** (including fund look-through) and **Bulk Concentration** (including single-position weight, Top-N holdings, and the Herfindahl-Hirschman Index). All calculations will be fully **epoch-aware** to guarantee data consistency.

-----

## 2\. Decision

We will implement the Concentration Analytics Engine by creating a new, stateless shared library (`concentration-analytics-engine`) to encapsulate all financial logic. This engine will be orchestrated by a new `ConcentrationService` within the existing `query-service`. This approach aligns with our established architectural pattern for on-the-fly analytics, ensuring high testability and separation of concerns. The feature will be exposed via a single, consolidated `POST` endpoint to provide an efficient and flexible client experience.

-----

## 3\. Architectural Consequences

### Pros:

  * **Architectural Consistency**: Follows the proven pattern of our `risk-analytics-engine` and `performance-calculator-engine`, making the new component familiar and easy to maintain.
  * **High Testability**: Isolating the complex financial logic into a pure, stateless library with no I/O operations allows for comprehensive and reliable unit testing.
  * **Improved Risk Insights**: Delivers a critical new dimension of risk analysis that is essential for prudent portfolio management and sophisticated client reporting.
  * **Client Efficiency**: A single, consolidated API endpoint allows front-end applications to fetch multiple concentration metrics in a single network call, which is highly efficient.

### Cons / Trade-offs:

  * **Increased Data Dependency**: The accuracy of the analytics, particularly issuer concentration with look-through, is highly dependent on the quality and availability of external data (e.g., issuer hierarchies, fund holdings).
  * **Potential for High Latency**: On-the-fly look-through calculations for portfolios with many nested funds can be computationally expensive and may lead to slower API response times for complex requests.

-----

## 4\. Architectural Design

### 4.1. Core Components

  * **New `concentration-analytics-engine` Library**: A new library will be created in `src/libs/` to encapsulate all complex concentration logic. It will contain no I/O operations, ensuring it is stateless, deterministic, and highly testable.
  * **`query-service` Integration**: A new `ConcentrationService` will be added to `query-service` to orchestrate data fetching from repositories, call the new engine for calculations, and format the API response.

### 4.2. Data Consistency (Epoch-Awareness)

To guarantee atomic consistency with all other analytics, the `ConcentrationService` will be strictly **epoch-aware**. All queries that fetch position data (e.g., via `PositionRepository`) **must** join with the `position_state` table and filter on `table.epoch = position_state.epoch`. This ensures that concentration figures are always calculated against the latest, complete version of the portfolio's data, preventing inconsistencies with other reports.

### 4.3. Data Sourcing

The `ConcentrationService` will fetch a superset of all required data in a single, parallelized operation (`asyncio.gather`) to minimize database round-trips. This includes:

  * Latest positions from `PositionRepository`.
  * Instrument details (including issuer data) from `InstrumentRepository`.
  * FX rates from `FxRateRepository`.
  * Look-through holdings data (from a new repository method to be created).

-----

## 5\. Key Methodologies

### 5.1. Issuer Concentration

This measures the total exposure to a single corporate entity, rolled up to its ultimate parent. For funds, it will apply a "look-through" to the underlying holdings. If look-through data is unavailable, the fund itself will be treated as the issuer.

### 5.2. Bulk Concentration

This measures the portfolio's overall level of diversification using standard industry metrics based on position weights ($w\_i$).

  * **Single-Position Concentration**: The weight of the single largest position in the portfolio, $w\_{(1)}$.
  * **Top-N Concentration ($CR\_N$)**: The sum of the weights of the largest N positions (e.g., Top-5, Top-10).
    $$CR_N = \sum_{i=1}^{N} w_{(i)}$$
  * **Herfindahl-Hirschman Index (HHI)**: The sum of the squared weights of all positions. A value approaching 1 indicates a highly concentrated portfolio.
    $$HHI = \sum_{i=1}^{N} w_i^2$$

-----

## 6\. API Specification (`query-service`)

  * **Method**: `POST`
  * **Path**: `/portfolios/{portfolio_id}/concentration`

### Request Body

```json
{
  "scope": {
    "as_of_date": "2025-08-31",
    "reporting_currency": "USD"
  },
  "metrics": [
    "ISSUER",
    "BULK"
  ],
  "options": {
    "lookthrough_enabled": true,
    "issuer_top_n": 10,
    "bulk_top_n": [5, 10]
  }
}
```

### Response Body

```json
{
  "scope": {
    "as_of_date": "2025-08-31",
    "reporting_currency": "USD"
  },
  "summary": {
    "portfolio_market_value": 12500000.00,
    "findings": [
      { "level": "BREACH", "message": "Issuer 'XYZ Group' at 15.3% exceeds the 10% limit." },
      { "level": "WARN", "message": "Top 10 holdings make up 62% of the portfolio, exceeding the 60% warning threshold." }
    ]
  },
  "issuer_concentration": {
    "top_exposures": [
      {
        "issuer_name": "XYZ Group",
        "exposure": 1912500.00,
        "weight": 0.153,
        "flag": "BREACH"
      }
    ]
  },
  "bulk_concentration": {
    "top_n_weights": {
      "5": 0.48,
      "10": 0.62
    },
    "single_position_weight": 0.18,
    "hhi": 0.18,
    "flag": "WARN"
  }
}
```

-----

## 7\. Observability

To monitor this new feature, the following will be implemented:

  * **Structured Logging**: All logs will be tagged with `portfolio_id` and `correlation_id`.
  * **Prometheus Metrics**:
      * `concentration_calculation_duration_seconds`: A `Histogram` to measure the end-to-end latency of a full concentration calculation, labeled by `portfolio_id`.
      * `concentration_lookthrough_requests_total`: A `Counter` to track how often the fund look-through feature is used.

-----

## 8\. Implementation Plan

  * **Phase 1: Foundation (Library & Data)**
    1.  Create the new `concentration-analytics-engine` library skeleton.
    2.  Enhance existing repositories in `query-service` to efficiently fetch the required superset of data (e.g., look-through holdings, issuer hierarchies). This may require new data models for issuer relationships.
  * **Phase 2: Core Logic & API**
    1.  Implement the **Issuer** and **Bulk** (Single-Position, Top-N, HHI) concentration logic within the new engine library, with comprehensive unit tests.
    2.  Build the `ConcentrationService` and the `POST /concentration` endpoint in `query-service`.
  * **Phase 3: Future Enhancements (v1.1)**
    1.  Implement **Counterparty** concentration logic.
    2.  Expand configuration options (e.g., allowing `face_value` vs. `market_value` for bond exposures).

-----

## 9\. Risks & Mitigations

  * **Data Quality**: The accuracy is highly dependent on the quality of underlying holdings and issuer hierarchy data.
      * **Mitigation**: The engine will fail gracefully. If look-through or hierarchy data is missing, it will fall back to using the direct issuer and flag this in the response.
  * **Performance**: Look-through calculations can be computationally expensive.
      * **Mitigation**: The engine will enforce a maximum look-through depth and all data transformations will be vectorized for performance.