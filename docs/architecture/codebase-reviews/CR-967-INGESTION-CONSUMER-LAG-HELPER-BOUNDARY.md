# CR-967: Ingestion Consumer Lag Helper Boundary

Date: 2026-06-05

## Scope

Move consumer-lag DLQ aggregation, severity classification, backlog summary stitching, and response
assembly into a dedicated helper module without changing public service behavior, endpoint response
fields, lookback filtering, ordering, or backlog propagation.

## Finding

`IngestionJobService.get_consumer_lag` mixed DLQ aggregate query construction, severity policy,
row-to-DTO mapping, health-summary lookup, and response assembly in one B-ranked service method.
The method is operational telemetry used for consumer pressure diagnostics, so this refactor keeps
the public service boundary stable and extracts only the reusable telemetry construction.

## Action

Added `ingestion_consumer_lag.py` with `load_consumer_lag_response`,
`classify_consumer_lag_severity`, and `build_consumer_lag_response`. The service method now passes
the session factory and `get_health_summary` callback into the helper, preserving behavior and the
existing service-level test seam.

## Result

`IngestionJobService.get_consumer_lag` improved from `B (6)` to `A (1)`. The extracted helper
module reports `A (55.85)` maintainability. `ingestion_job_service.py` shrank from 1,116 SLOC to
1,077 SLOC and improved from `B (12.63)` to `B (13.77)`.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py -q`
  => 16 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_consumer_lag.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_consumer_lag.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => passed after formatting touched files
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_consumer_lag.py`
  => `ingestion_job_service.py` 1,077 SLOC; `ingestion_consumer_lag.py` 76 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_consumer_lag.py -s`
  => `ingestion_job_service.py` `B (13.77)`; `ingestion_consumer_lag.py` `A (55.85)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal telemetry helper extraction that preserves
public API contracts, consumer-lag semantics, and operator-facing documentation truth.
