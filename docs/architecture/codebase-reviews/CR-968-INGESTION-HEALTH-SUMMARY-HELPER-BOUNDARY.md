# CR-968: Ingestion Health Summary Helper Boundary

Date: 2026-06-05

## Scope

Move ingestion health-summary aggregate counts, oldest-backlog lookup, backlog total calculation,
and response assembly into a dedicated helper module without changing the public service method or
operator-facing response fields.

## Finding

`IngestionJobService.get_health_summary` mixed aggregate SQL construction, count normalization,
oldest-backlog lookup, backlog calculation, and DTO assembly in one B-ranked service method. The
method is reused by other telemetry surfaces, including consumer lag, so keeping a narrow reusable
helper improves service readability and reduces repeated operational summary logic.

## Action

Added `ingestion_health_summary.py` with `load_health_summary_response`. The service method now
delegates to the helper while passing the service module's session factory, preserving the existing
test monkeypatch seam and public method contract.

## Result

`IngestionJobService.get_health_summary` improved from `B (6)` to `A (1)`. The extracted helper
module reports `A (60.46)` maintainability. `ingestion_job_service.py` shrank from 1,077 SLOC to
1,045 SLOC and improved from `B (13.77)` to `B (15.15)`. Only
`IngestionJobService.get_idempotency_diagnostics` remains B-ranked in the service.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py -q`
  => 17 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_health_summary.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_health_summary.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => passed after formatting touched files
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_health_summary.py`
  => `ingestion_job_service.py` 1,045 SLOC; `ingestion_health_summary.py` 41 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_health_summary.py -s`
  => `ingestion_job_service.py` `B (15.15)`; `ingestion_health_summary.py` `A (60.46)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal health-summary helper extraction that
preserves public API contracts, health-summary semantics, and operator-facing documentation truth.
