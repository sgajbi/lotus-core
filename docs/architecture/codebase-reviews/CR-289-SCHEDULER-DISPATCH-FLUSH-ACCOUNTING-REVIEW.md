# CR-289: Scheduler dispatch flush accounting

Date: 2026-03-14

## Summary
- Hardened valuation and aggregation scheduler dispatch loops so partial Kafka dispatch failure and
  flush-timeout uncertainty are now explicit instead of silently under-accounted.

## Problem
- Both scheduler dispatch loops:
  - `ValuationScheduler._dispatch_jobs(...)`
  - `AggregationScheduler._dispatch_jobs(...)`
  used a direct `publish_message(...)` loop followed by bare `flush(timeout=10)`.
- That left two real runtime gaps:
  - a synchronous publish failure mid-loop aborted before the already-queued jobs were flushed
  - positive `flush(timeout=10)` results were ignored instead of becoming explicit dispatch failures
- Those are exactly the delivery-accounting failure modes we already hardened in ingestion, outbox,
  and replay paths.

## Change
- Updated both scheduler dispatch loops to:
  - flush already-queued jobs even when a later publish raises synchronously
  - raise explicit runtime errors describing the remaining undispatched job keys
  - treat positive `flush(timeout=10)` results as explicit delivery-confirmation failure
- Added deterministic job-key strings so failure messages point at the concrete affected work.

## Why this matters
- These schedulers own hot runtime queue dispatch paths.
- If dispatch semantics are weak here, jobs can get stranded in an ambiguous state where:
  - some work may already be queued
  - later work definitely is not
  - logs do not say which is which
- This change improves runtime trust and makes later stale-reset behavior less opaque.

## Evidence
- Unit proofs:
  - `tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
  - `tests/unit/services/portfolio_aggregation_service/core/test_aggregation_scheduler.py`
- Proves for both schedulers:
  - partial dispatch failure still flushes queued work
  - the raised error includes the remaining job keys
  - positive flush timeout becomes an explicit failure

## Validation
- `python -m pytest tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py tests/unit/services/portfolio_aggregation_service/core/test_aggregation_scheduler.py -q`
- `python -m ruff check src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py tests/unit/services/portfolio_aggregation_service/core/test_aggregation_scheduler.py`

## Follow-up
- The next meaningful step in this family is the same standard for any remaining scheduler or
  consumer-side Kafka publish loop that still assumes “no exception” means delivery is fully
  accounted.
