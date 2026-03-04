### **RFC 024: Ensure Atomic Portfolio Time-Series Aggregation**

* **Status**: **Final**
* **Date**: 2025-09-02
* **Lead**: Gemini Architect
* **Services Affected**: `timeseries_generator_service`, `position-valuation-calculator`

---

## 1. Summary (TL;DR)

A critical data integrity flaw exists in the `timeseries_generator_service` due to a race condition. Portfolio-level aggregation for a given day can execute before all constituent `position_timeseries` records for that day are generated, resulting in a permanently incorrect `portfolio_timeseries` record based on partial data.

This RFC finalizes the decision to implement a **manifest-based approach** to make the aggregation trigger deterministic, guaranteeing correctness by ensuring all required data is present before aggregation runs.

---

## 2. Decision

We will implement a manifest-based aggregation trigger to eliminate the identified race condition. A new `daily_aggregation_manifest` table will be introduced to store the expected count of position time-series records for each portfolio-day. The `position-valuation-calculator` will be responsible for creating these manifest entries, and the `timeseries_generator_service` will be modified to consult this manifest before claiming an aggregation job, proceeding only when the actual record count matches the expected count.

---

## 3. The Flaw: The Race Condition

The existing process is flawed due to its non-deterministic trigger mechanism:

1.  The `PositionTimeseriesConsumer` processes a snapshot for `(Portfolio P1, Security S1, Date D)` and creates a `position_timeseries` record. It then idempotently creates a `portfolio_aggregation_job` for `(P1, D)`.
2.  If `P1` has 10 positions on Date `D`, this process will happen 10 times, repeatedly upserting the same `(P1, D)` job.
3.  The `AggregationScheduler` runs on its own schedule. It might claim and dispatch the job for `(P1, D)` after only one of the 10 `position_timeseries` records has been created.
4.  The `PortfolioTimeseriesConsumer` then executes, faithfully aggregating the *one* record it can find, and writes an incorrect `portfolio_timeseries` record to the database. This error silently propagates to all downstream analytics.

---

## 4. Architectural Consequences

### Pros

* **Guaranteed Correctness**: This solution completely eliminates the race condition. Portfolio-level aggregation will only run when its complete set of constituent data is present.
* **Determinism & Auditability**: The system's behavior becomes predictable and auditable. The manifest provides an explicit record of the work expected for each aggregation, making it easy to debug why a job may be pending.
* **Architectural Alignment**: This approach aligns with existing system patterns of using the database for durable, explicit state management (e.g., the `reprocessing_jobs` table) rather than relying on implicit event timing.

### Cons

* **Increased Complexity**: This introduces a new table and adds logic to the `ValuationScheduler` in an upstream service. This is a necessary and justified trade-off for guaranteeing data integrity.

---

## 5. High-Level Design

### 5.1. Data Model Changes

An Alembic migration will be created to add the following new table.

**New Table: `daily_aggregation_manifest`**

| Column             | Type        | Description                                                                  |
| :----------------- | :---------- | :--------------------------------------------------------------------------- |
| `portfolio_id`     | `VARCHAR` (PK) | The portfolio's unique identifier.                                           |
| `aggregation_date` | `DATE` (PK)    | The date for the aggregation.                                                |
| `expected_count`   | `INTEGER`   | The number of `position_timeseries` records that must exist to run.          |
| `status`           | `VARCHAR`   | `PENDING`, `COMPLETE`. Tracks the lifecycle of the manifest itself.            |
| `created_at`       | `TIMESTAMPZ` | Standard timestamp for record creation.                                      |
| `updated_at`       | `TIMESTAMPZ` | Standard timestamp for record updates.                                       |

### 5.2. Logic Changes

1.  **Manifest Creation (`position-valuation-calculator` service)**
    * The **`ValuationScheduler`** is the authoritative source for knowing how many positions are open for a portfolio on a given day.
    * When it creates the backfill valuation jobs for a portfolio for day `D`, it will be modified to also perform an **idempotent upsert** into the `daily_aggregation_manifest` table.
    * It will set the `portfolio_id`, `aggregation_date`, and the `expected_count` based on the number of open positions it found. The `status` will be `PENDING`.

2.  **Modify Scheduler Eligibility (`timeseries_generator_service` service)**
    * The `find_and_claim_eligible_jobs` method in the `TimeseriesRepository` will be enhanced with a new eligibility check.
    * Before claiming a `portfolio_aggregation_job` for `(P1, D)`, the query will now perform a `JOIN` with the `daily_aggregation_manifest` table and the `position_timeseries` table.
    * The job for `(P1, D)` will only be considered eligible if the count of `position_timeseries` records for that key matches the `expected_count` in the manifest.

---

## 6. Observability

To monitor the health of this new mechanism, the following metric will be added:

* **New Metric**: A Prometheus `Gauge` named `timeseries_aggregation_pending_manifests` will be added. The `AggregationScheduler` will periodically update this gauge to report the number of manifests still in a `PENDING` state, providing visibility into any aggregation backlogs.

---

## 7. Testing Plan

* **Unit Tests**:
    * A new unit test for the `ValuationScheduler` will verify that it correctly calculates the expected count and calls a new repository method to upsert the manifest.
    * A new unit test for the `AggregationScheduler`'s repository (`TimeseriesRepository`) will verify that the `find_and_claim_eligible_jobs` query correctly joins the tables and respects the count constraint.
* **Integration Tests**:
    * An integration test will be created for the `ValuationScheduler` to confirm it can successfully write a manifest record to the test database.
    * An integration test for the `AggregationScheduler` will seed the database with a manifest, a job, and a partial set of `position_timeseries` records, asserting that the job is **not** claimed. It will then add the remaining records and assert that the job **is** claimed on the next run.
* **End-to-End Test**:
    * A new E2E test will be created (`tests/e2e/test_timeseries_atomicity.py`). This test will:
        1.  Ingest a portfolio with multiple (e.g., 3) positions.
        2.  Ingest a business date and market prices to trigger valuation and timeseries generation for all 3 positions.
        3.  Poll the database to verify that the `daily_aggregation_manifest` is created with `expected_count = 3`.
        4.  Poll to verify that all 3 `position_timeseries` records are created.
        5.  Finally, poll to verify that the `portfolio_timeseries` record is created and that its `eod_market_value` correctly reflects the sum of all three positions, proving the aggregation was atomic.

---

## 8. Acceptance Criteria

* The `daily_aggregation_manifest` table is created via an Alembic migration.
* The `ValuationScheduler` is updated to create manifest records with the correct `expected_count`.
* The `AggregationScheduler`'s eligibility query in `TimeseriesRepository` is updated to use the manifest and count check.
* All new unit, integration, and E2E tests pass.
* The **documentation is updated** to reflect the new, guaranteed-correct behavior:
    * `docs/features/timeseries_generator/01_Feature_Timeseries_Generator_Overview.md`: The "Gaps and Design Considerations" section detailing the race condition is removed and replaced with a description of the new manifest-based atomic aggregation.
    * `docs/features/timeseries_generator/03_Methodology_Guide.md`: The description of the portfolio aggregation process is updated to include the role of the manifest.
    * `docs/features/timeseries_generator/04_Operations_Troubleshooting_Guide.md`: The troubleshooting guide is updated. The section on incorrect figures due to the race condition is removed. A new section is added explaining how to debug a pending aggregation by checking the `daily_aggregation_manifest` against the actual count in `position_timeseries`. The new Prometheus metric is documented.