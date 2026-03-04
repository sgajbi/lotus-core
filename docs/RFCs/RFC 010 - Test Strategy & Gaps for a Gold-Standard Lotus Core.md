### RFC 010: Test Strategy for a Gold-Standard Lotus Core

* **Status**: Proposed
* **Date**: 2025-08-30
* **Scope**: All services and libraries in the monorepo

---
## 1. Executive Summary

Our system's test suite has a solid foundation, but to achieve a gold-standard, enterprise-grade level of quality, we must go beyond testing individual components in isolation. We must test the resilience and integrity of the system *as a whole*.

This RFC expands our test strategy to include a new pillar: **System-Level Resilience & Integrity Testing**. This introduces **Chaos Testing** to validate our resilience to infrastructure failure, **Load and Stress Testing** to understand our performance bottlenecks, and a **Data Integrity Auditing** tool to independently verify the correctness of our entire event-driven pipeline.

These advanced testing methodologies, combined with targeted enhancements to our existing unit and integration tests, will provide maximum confidence in our system's correctness, scalability, and robustness in a production environment.

---
## 2. Gaps & Proposed Enhancements in Core Testing

We will first address the gaps in our existing test pyramid to ensure foundational correctness.

### 2.1. Epoch-Aware Data Correctness
* **Gap**: Insufficient testing of our epoch-fencing logic, a critical component for preventing data corruption during reprocessing.
* **Solution**: Implement new integration tests for the `SummaryRepository` that seed the database with data across multiple epochs and assert that queries only return data from the single, correct, active epoch.

### 2.2. Resilience to Partial Failures
* **Gap**: The negative paths of our outbox and consumer retry mechanisms are not validated.
* **Solution**:
    * **Outbox**: Create an integration test where the mock Kafka producer simulates partial delivery failure and assert that the `OutboxDispatcher` correctly updates event statuses and `retry_count`.
    * **Consumers**: Add a test that proves consumer idempotency by delivering the same message twice and asserting that no duplicate data is created.

### 2.3. Financial Engine Correctness
* **Gap**: Our financial engines lack sufficient testing for edge cases and mathematical invariants.
* **Solution**:
    * **`risk-analytics-engine`**: Add unit tests for all remaining metrics: Sharpe, Sortino, Beta, Tracking Error, Information Ratio, and all VaR methods.
    * **`performance-calculator-engine`**: Introduce **property-based testing** using `hypothesis` to verify core invariants, such as scaling invariance (the rate of return should not change if all monetary values are multiplied by a constant factor).

---
## 3. New Pillar: System-Level Resilience & Integrity Testing

This new category of testing focuses on the non-functional, systemic behavior of our platform.

### 3.1. Chaos Testing
We will build a harness to deliberately inject failures into a running staging environment to verify our system's resilience.
* **Target Scenarios**:
    * **Kafka Unavailability**: Temporarily bring down a Kafka broker. We will assert that services with stateful consumers pause and resume gracefully, and the outbox dispatcher handles the connection failure without message loss.
    * **Database Failover**: Simulate a database primary node failure. We will assert that the `query-service` successfully connects to the read-replica and that write-oriented services recover once the primary is restored.
    * **Service Failure**: Randomly terminate pods for our calculator microservices. We will assert that Kafka consumer group rebalancing works correctly and that another instance picks up the work without creating duplicate data.

### 3.2. Load and Stress Testing
We will use tooling (e.g., k6, Locust) to simulate high-load scenarios and identify performance bottlenecks.
* **Target Scenarios**:
    * **Ingestion Throughput**: Determine the maximum sustainable rate of transaction ingestion before Kafka consumer lag grows uncontrollably.
    * **Reprocessing "Thundering Herd"**: Simulate a back-dated price update for a universally held security (like an index ETF) that triggers reprocessing for thousands of keys simultaneously. We will measure the system's recovery time and ensure it does not lead to cascading failures.
    * **Query API Concurrency**: Stress test the `POST /review` endpoint with hundreds of concurrent requests to identify database connection pool limits and performance degradation curves.

### 3.3. Data Integrity Auditing
We will build a new, independent, offline tool that acts as a final source of truth for data correctness.
* **Mechanism**: This tool will bypass the event-driven pipeline entirely. For a given portfolio, it will read the raw, persisted transaction log from the database and recalculate the final state (e.g., final position quantity and cost basis) using a clean, independent implementation of the business logic.
* **Assertion**: The tool will compare its calculated result against the final state stored in the `daily_position_snapshots` table. Any discrepancy is a critical bug that indicates a flaw in our event-driven pipeline (e.g., a missed event, a race condition, or an epoch-fencing error). This provides an end-to-end guarantee of correctness that no other test can.

---
## 4. Implementation Plan

1. **Phase 1 - Foundational Correctness**: Implement all tests outlined in Section 2 (Epoch-Awareness, Partial Failures, Financial Engines).
2. **Phase 2 - Advanced Tooling**:
    * Build the scripting and infrastructure for Load and Stress Testing scenarios.
    * Develop the first version of the offline Data Integrity Auditing tool.
3. **Phase 3 - Chaos Engineering**:
    * Develop the Chaos Testing harness and begin running automated failure injection tests in our staging environment.

---
## 5. Acceptance Criteria

* All unit and integration test gaps are closed.
* The system can withstand the sudden failure and recovery of Kafka and PostgreSQL without data loss.
* Performance benchmarks for ingestion and reprocessing are established and monitored.
* The Data Integrity Auditing tool runs successfully and finds no discrepancies on a regular basis.
* The full E2E and System-Level Resilience test suites pass, providing a gold-standard signal of production readiness.