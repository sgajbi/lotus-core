# CR-012 Shared Worker Runtime Utility Convergence Review

## Scope

Review duplicated worker runtime scaffolding across post-RFC-81 service runtimes and extract only the low-risk shared supervision logic.

Reviewed areas:

- `src/services/*/app/consumer_manager.py`
- `src/libs/portfolio-common/portfolio_common/runtime_supervision.py`
- corresponding unit runtime-manager tests

## Findings

### 1. Service wiring differs, but shutdown supervision was duplicated almost verbatim

Across worker runtimes, the following pattern was repeated:

- wait for shutdown signal or task failure
- call `consumer.shutdown()` for all consumers
- stop service-local dispatcher/scheduler/reprocessing worker callbacks
- set `server.should_exit = True`
- `await asyncio.gather(*tasks, return_exceptions=True)`

This duplication existed in:

- calculator worker runtimes
- `timeseries_generator_service`
- `portfolio_aggregation_service`
- `pipeline_orchestrator_service`
- `financial_reconciliation_service`
- `persistence_service`
- `valuation_orchestrator_service`

### 2. Full base-class extraction is not justified yet

The runtimes still differ materially in:

- consumer composition
n- required topics
- scheduler/dispatcher/reprocessing-worker presence
- web app port and app instance wiring

A generic `BaseConsumerManager` would increase indirection without eliminating enough service-specific logic.

### 3. The correct convergence point is the shutdown tail

The low-risk, high-value reuse point is the terminal shutdown sequence, not manager construction or task wiring.

## Action taken

Implemented in the review program:

- added shared helper:
  - `portfolio_common.runtime_supervision.shutdown_runtime_components(...)`
- updated worker runtimes to use the shared helper for:
  - consumer shutdown
  - service-local stop callbacks
  - uvicorn server exit signaling
  - bounded task gather
- added direct shared-helper unit coverage in:
  - `tests/unit/libs/portfolio-common/test_runtime_supervision.py`

## Sign-off state

Current state: `Hardened`

Reason:

- meaningful runtime duplication reduced
- no generic base class introduced prematurely
- existing service-runtime tests still validate service-specific lifecycle behavior
