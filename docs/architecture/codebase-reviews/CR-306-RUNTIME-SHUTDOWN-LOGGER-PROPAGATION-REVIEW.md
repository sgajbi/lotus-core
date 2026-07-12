# CR-306 Runtime Shutdown Logger Propagation Review

## Summary

`shutdown_runtime_components(...)` now logs callback-failure and forced-cancellation evidence,
but most service `ConsumerManager` call sites still did not pass their service logger through.

## Why This Matters

Without logger propagation, the shared runtime hardening from `CR-305` exists in code but not in
service-level operational evidence. That weakens the value of the shared fix exactly where
operators need it during teardown incidents.

## Change

- updated all `ConsumerManager` call sites that use `shutdown_runtime_components(...)` to pass:
  - `logger=logger`
- covered service families:
  - persistence
  - valuation orchestrator
  - portfolio aggregation
  - pipeline orchestrator
  - financial reconciliation
  - timeseries generator
  - position, valuation, cost, and cashflow calculators

## Evidence

- touched-surface lint:
  - `python -m ruff check ...consumer_manager.py`
    - passed
- representative runtime pack:
  - `python -m pytest tests/unit/services/portfolio_aggregation_service/unit/test_portfolio_aggregation_consumer_manager_runtime.py tests/unit/services/valuation_orchestrator_service/unit/test_valuation_orchestrator_consumer_manager_runtime.py tests/unit/services/pipeline_orchestrator_service/unit/test_pipeline_orchestrator_consumer_manager.py tests/unit/services/persistence_service/core/test_persistence_consumer_manager_runtime.py -q`
    - `8 passed`

## Follow-up

- if we need stronger proof later, add one service-level assertion that a shutdown callback failure
  is actually emitted through the service logger. The propagation rollout is now complete.
