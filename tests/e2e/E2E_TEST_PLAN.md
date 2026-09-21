# E2E Test Plan for Lotus Core

## 1. Philosophy and Goals

This document outlines the end-to-end (E2E) testing strategy for the system. The goal is not to achieve 100% coverage, but to create a minimal, high-signal suite that provides maximum confidence in the correctness and resilience of critical, cross-service user journeys.

### Core Principles:
- **Deterministic**: Tests must be 100% repeatable and free of flakiness. This is achieved through full state isolation, unique test data, and robust polling mechanisms instead of fixed-time waits.
- **User-Centric**: Each test represents a real-world business scenario (e.g., "a multi-day trading sequence," "correcting a historical trade").
- **Production-like**: All tests run against the full Docker Compose stack, using real HTTP APIs, a real database, and a real Kafka broker.

## 2. Scenario Inventory

The following critical paths will be covered by the E2E test suite.

### Happy Path Scenarios
- **`test_valuation_pipeline.py` (Implemented)**: Validates the fundamental data flow from ingestion to a single day's position valuation.
- **`test_5_day_workflow.py` (Current)**: Simulates a realistic multi-day sequence of deposits, buys, sells, and dividends, verifying the final state and realized P&L calculations.
- **`test_dual_currency_workflow.py`**: Validates the system's ability to handle a portfolio in one currency (e.g., USD) trading an instrument in another (e.g., EUR), ensuring all FX conversions for cost basis, P&L, and valuation are correct.
- **`test_avco_workflow.py`**: Verifies the entire pipeline for a portfolio explicitly configured to use the Average Cost (AVCO) accounting method.
- **`test_complex_portfolio_lifecycle.py`**: End-to-end portfolio lifecycle with mixed cashflows, multi-currency trades, FX gaps, supported source-data and position reads, and explicit disabled-route checks where legacy analytics moved to another product.

### Retired Query Routes
- **`test_concentration_pipeline.py` and `test_review_pipeline.py`**: Call the live Core query HTTP surface to verify migrated concentration and review routes remain unavailable under the RFC 056 `404`/`410` compatibility policy. A `404` also probes GET so an active POST route returning portfolio-not-found does not pass. They do not seed portfolios, transactions, or valuations. The fast ASGI counterpart inspects registered routes, including hidden routes, and proves the guard rejects a restored POST route.

### Reprocessing Scenarios
- **`test_reprocessing_workflow.py`**: Simulates an initial state over several days, then ingests a back-dated transaction. Asserts that the system correctly triggers an epoch increment, re-processes the history, and arrives at the correct final state with accurate P&L.
- **`test_rapid_reprocessing.py`**: Tests the system's resilience to race conditions by ingesting two different back-dated transactions in quick succession, verifying that the epoch fencing works and the final state is correct.

### Resilience & Idempotency Scenarios
- **`test_reliability_pipeline.py`**:
  - **Idempotency**: Verifies that ingesting the exact same data entities (e.g., an instrument) twice does not create duplicate records.
  - **Tenant-owned transaction admission**: Verifies that a transaction is refused before its portfolio is durably visible to the admitted tenant, then accepted after a supported tenant-scoped read confirms materialization. A `202` portfolio ingest is queue acknowledgement, not durable ownership proof.
