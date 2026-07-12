# CR-015 Web Worker Startup Contract Review

## Scope

Web-backed worker runtimes that expose `/metrics` and run a `ConsumerManager`
inside `main.py`.

## Findings

These services all implemented the same operational contract independently:

- log startup
- instrument the web app for Prometheus
- run a `ConsumerManager`
- log critical runtime failure
- log shutdown

The duplication was not just cosmetic. Runtime semantics had already drifted:

- some worker services re-raised fatal runtime exceptions
- others logged critical errors and then exited without re-raising

That is the wrong contract split for worker runtimes. A fatal `ConsumerManager`
failure should terminate the process uniformly so orchestration can restart it
and operators see a hard failure instead of a misleading clean exit.

## Actions taken

- Extracted the shared contract into
  `portfolio_common.worker_runtime.run_instrumented_worker_service(...)`
- Moved these worker services onto the shared helper:
  - `cashflow_calculator_service`
  - `cost_calculator_service`
  - `position_calculator`
  - `position_valuation_calculator`
  - `timeseries_generator_service`
  - `portfolio_aggregation_service`
  - `valuation_orchestrator_service`
  - `pipeline_orchestrator_service`
- Standardized behavior so fatal worker runtime errors are logged and re-raised
  consistently.
- Added unit tests for the shared helper.

## Rationale

This helper is justified because the contract is genuinely shared:

- same runtime shape
- same metrics exposure
- same error semantics
- same shutdown semantics

This is a good abstraction. It removes drift without forcing unrelated services
like `persistence_service` or pure HTTP apps into the same model.

## Evidence

- `src/libs/portfolio-common/portfolio_common/worker_runtime.py`
- worker `main.py` files listed above
- `tests/unit/libs/portfolio-common/test_worker_runtime.py`
