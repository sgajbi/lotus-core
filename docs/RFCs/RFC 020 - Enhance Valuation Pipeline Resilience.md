# RFC 020: Enhance Valuation Pipeline Resilience

* **Status**: Proposed
* **Date**: 2025-09-01
* **Related RFCs**: RFC 003

## 1. Summary

The `position-valuation-calculator` is a critical service, but its current implementation has two key weaknesses. First, transient data availability issues (e.g., a late-arriving FX rate feed) cause permanent job failures, requiring manual intervention to fix. Second, the dual responsibilities of real-time event consumption and heavy background scheduling are coupled within a single service, creating a scalability risk.

This RFC proposes two enhancements:
1.  Make the `ValuationConsumer` self-healing by introducing a retry mechanism for jobs that fail due to missing reference data.
2.  Improve system scalability and resilience by splitting the `ValuationScheduler` into its own dedicated microservice.

## 2. Gaps and Proposed Solutions

### 2.1. Resilience: Permanent Failure on Transient Data Gaps

* **Gap:** When a `ValuationConsumer` processes a job but cannot find a required market price or FX rate, it correctly marks the underlying `daily_position_snapshot` as `FAILED`. However, it then marks the `portfolio_valuation_job` as `COMPLETE`. This is a terminal state. If the missing data arrives moments later, the system does not automatically re-attempt the valuation.
* **Proposal:**
    1.  **Modify Consumer Logic:** The `ValuationConsumer` will be updated to distinguish between permanent errors and transient `DataNotFoundError` exceptions (for prices/FX).
    2.  **Durable Job Lifecycle:** When a `DataNotFoundError` occurs, the consumer will **not** mark the job as `COMPLETE`. Instead, it will update the job record to increment the `attempt_count` and set `failure_reason`, but leave the `status` as `PENDING`.
    3.  **Delayed Retry:** The `ValuationScheduler` will be modified to ignore `PENDING` jobs where `attempt_count > 0` for a configurable backoff period (e.g., 10 minutes), preventing rapid, pointless retries.
    4.  **Alerting:** A Prometheus alert will be configured to fire if a job's `attempt_count` exceeds a threshold (e.g., 5), notifying the operations team of a persistent data availability issue.

### 2.2. Scalability: Coupling of Workloads

* **Gap:** The service combines two different workload profiles: a low-latency, event-driven consumer and a potentially high-latency, CPU/IO-intensive batch scheduler. A long-running scheduling cycle (e.g., fanning out a price update for an ETF) could starve the consumer of resources, delaying the processing of real-time valuation jobs.
* **Proposal:**
    1.  **Create New `valuation-scheduler-service`:** A new, dedicated microservice will be created. All logic from the `ValuationScheduler` class will be moved into this new service.
    2.  **Simplify `position-valuation-calculator`:** This service will become a pure, lightweight consumer. Its only responsibility will be to process `valuation_required` and `market_price_persisted` events. This allows it to be scaled out easily based on the volume of valuation work.
    3.  **Independent Scaling:** This separation allows each component to be scaled independently. The scheduler can run as a single instance, while the calculator can be scaled to many instances to handle high throughput.