# CR-308 Worker Runtime Startup Failure Classification Review

## Summary

`run_instrumented_worker_service(...)` only wrapped `manager.run()` in its shared critical-error
path. If Prometheus instrumentation setup failed before the manager started, the service crashed
without the standard worker-runtime critical log.

## Why This Matters

This helper is shared by worker-style services. Startup instrumentation failure is still a service
startup failure and should be classified with the same service-level critical evidence as runtime
manager crashes.

## Change

- moved metrics instrumentation inside the shared `try/except`
- startup instrumentation failure now:
  - logs through the shared critical service path
  - re-raises
  - still emits the shared final shutdown log

## Evidence

- added direct unit proof in:
  - `tests/unit/libs/portfolio-common/test_worker_runtime.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_worker_runtime.py -q`
    - `3 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/worker_runtime.py tests/unit/libs/portfolio-common/test_worker_runtime.py`
    - passed

## Follow-up

- if we want a richer shared lifecycle contract later, the next step is making startup stage names
  explicit in the critical log path. The immediate classification gap is now closed.
