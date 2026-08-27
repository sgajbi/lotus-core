# ADR 002: Scalable and Resilient Reprocessing Engine

* **Status**: Implemented
* **Date**: 2025-09-01
* **RFC**: [RFC 018 - Enhance Reprocessing Scalability and Resilience](../RFCs/RFC%20018%20-%20Enhance%20Reprocessing%20Scalability%20and%20Resilience.md)

## Context and Problem Statement

The system's reprocessing engine is triggered under two conditions:
1.  A back-dated transaction arrives (`position-calculator`).
2.  A back-dated market price arrives (`position-valuation-calculator`).

The initial implementation had two architectural weaknesses:
* **Scalability ("Thundering Herd")**: A back-dated price for a widely-held security (e.g., an S&P 500 ETF) would cause the `ValuationScheduler` to perform a massive, synchronous, in-memory fan-out to reset watermarks for potentially thousands of portfolios. This could overwhelm the scheduler, block other tasks, and put extreme pressure on the database.
* **Resilience (Non-Atomic Replay)**: The `position-calculator` would increment a position's epoch in the database *before* re-emitting all historical transactions. A crash between these two steps would leave the position in an unrecoverable `REPROCESSING` state, requiring manual intervention.

## Decision

To address these gaps, we implemented the solutions proposed in RFC 018:

1.  **Introduce a Durable Job Queue**: We transformed the risky in-memory fan-out into a durable, asynchronous workflow. A new `reprocessing_jobs` table was introduced to act as a persistent queue for high-volume "Reset Watermark" tasks.
2.  **Implement a Dedicated Worker**: A new `ReprocessingWorker` was added to the `position-valuation-calculator` service. This worker consumes jobs from the `reprocessing_jobs` table in small, controlled batches, smoothing out the workload and protecting the system's stability.
3.  **Enforce Atomic Replay**: The `position-calculator` was refactored to use the existing **Outbox Pattern**. Now, incrementing the epoch and queueing the historical events for re-emission occur within the same atomic database transaction, guaranteeing resilience against service crashes.

## Consequences

### New Data Flow: Price-Based Reprocessing

The new flow for handling a back-dated price is now much more scalable and resilient:

```mermaid
sequenceDiagram
    participant PEC as PriceEventConsumer
    participant IRS as instrument_reprocessing_state (DB Table)
    participant VS as ValuationScheduler
    participant RJ as reprocessing_jobs (DB Table)
    participant RW as ReprocessingWorker
    participant PS as position_state (DB Table)

    PEC->>+IRS: Upserts a single trigger record <br/> (security_id, earliest_impacted_date)
    VS->>+IRS: Polls for new triggers
    IRS-->>-VS: Returns trigger
    VS->>+RJ: Creates one durable job <br/> (type: RESET_WATERMARKS, payload: {security_id, ...})
    VS->>-IRS: Deletes the consumed trigger
    
    RW->>+RJ: Polls for and claims pending jobs
    RJ-->>-RW: Returns claimed job
    RW->>PS: Finds all affected portfolios & <br/> bulk-updates their watermarks
    RW->>-RJ: Marks job as COMPLETE
````

### Benefits

  * **Scalability**: The system can now handle back-dated prices for securities held in tens of thousands of portfolios without risk of instability.
  * **Resilience**: The entire reprocessing trigger mechanism is now atomic and durable. Work is never lost, even if services crash.
  * **Observability**: The new `instrument_reprocessing_triggers_pending` metric provides a clear view of the backlog, and the `reprocessing_jobs` table gives operators full visibility and control over the fan-out process.
  * **Maintainability**: The separation of concerns is much cleaner. The scheduler's role is simplified, and the heavy lifting is isolated to a dedicated worker.

### Drawbacks

  * **Increased Complexity**: The introduction of a new table and a new worker adds components to the system. However, this complexity is justified by the significant gains in scalability and resilience.

<!-- end list -->

