# CR-1513: Cost Timeline Application Ownership

Date: 2026-07-11
Issue: #468
Status: Implemented locally; workflow and persistence extraction pending

## Objective

Move cost timeline orchestration into the target application layer without moving Prometheus,
clocks, SQL, or delivery behavior into domain/application code.

## Finding

The legacy `transaction_processor.py` coordinated parsing, deterministic ordering, calculation, and
open-lot results, so it was an application service rather than a standalone engine. Direct imports
of Prometheus histograms and `time.monotonic()` prevented a correct target-layer move.

## Implementation

- Moved and renamed the service to target-owned `CostBasisTimelineProcessor`.
- Added a framework-neutral `CostBasisCalculationObserver` port.
- Added a target infrastructure Prometheus adapter that preserves existing depth and duration
  metric names and isolates telemetry failures from financial processing.
- Wired production and AVCO reconciliation composition explicitly; uncomposed domain tests use a
  no-op observer without importing infrastructure.
- Moved processor tests to the target service and added adapter, strategy-selection, observation,
  error, incremental, backdated, and retirement-path proof.
- Corrected the compatibility-import inventory to ignore generated build output and removed its
  stale expectation that position processing still imports legacy calculator source.

## Compatibility

No calculation, API, event, database, metric name, label, or downstream contract changed. The
quarantined legacy consumer remains constructible because observer injection does not add a
workflow constructor. The old processor module and generic class/factory names are removed rather
than retained as aliases.

## Validation

- Target service, cost workflow/consumer, and private-banking AVCO cohort: `194 passed`.
- Repository-native transaction-processing contract: `32 passed in 126.82s`.
- Ruff, formatting, targeted MyPy, application-layer, dependency-inversion, domain-layer,
  testability, and in-process modularity gates passed.
- Reconciliation onto the post-PR-727 mainline passed `103` focused tests plus targeted MyPy,
  Ruff, and diff checks.

## Follow-Up

Split the transitional cost workflow into application use cases and infrastructure adapters behind
explicit repository and publication ports. Keep the current SQL repository and compatibility
consumer outside the target application package until their transaction and delivery boundaries
are extracted and proven separately.
