# CR-955: Ingestion SLO Status Helper Boundary

Date: 2026-06-05

## Scope

Move ingestion SLO snapshot loading and threshold response assembly out of
`ingestion_job_service.py` without changing SLO response shape, safe-default behavior, metric
emission, database aggregate preference, or fallback behavior for dialects without percentile
support.

## Finding

`IngestionJobService.get_slo_status` mixed session iteration, DB-side aggregate query construction,
fallback job scanning, percentile calculation, backlog-age calculation, warning/default handling,
metric emission, failure-rate calculation, and response assembly. The method reported `C (17)`
complexity and kept operational SLO calculation policy coupled to the broad ingestion service.

## Action

Added `ingestion_slo_status.py` with:

- `IngestionSloSnapshot`
- `load_ingestion_slo_snapshot`
- `slo_snapshot_from_jobs`
- `build_slo_status_response`

`ingestion_job_service.py` now keeps ownership of session iteration, warning/default handling, and
`INGESTION_BACKLOG_AGE_SECONDS` emission while delegating snapshot loading and threshold response
assembly to the helper module.

## Result

`get_slo_status` improved from `C (17)` to `A (3)`. `ingestion_job_service.py` shrank from 1,545
SLOC to 1,477 SLOC and remains `C (0.00)` under Radon maintainability, requiring additional
focused extractions. The new SLO helper module reports `A (42.76)` maintainability.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_slo_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py -q`
  => 21 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_slo_status.py tests\unit\services\ingestion_service\services\test_ingestion_slo_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_slo_status.py tests\unit\services\ingestion_service\services\test_ingestion_slo_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => 4 files already formatted
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_slo_status.py`
  => `ingestion_job_service.py` 1,477 SLOC; SLO helper 147 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_slo_status.py -s`
  => service `C (0.00)`, helper `A (42.76)`
- `python -m radon cc src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_slo_status.py -s`
  => `get_slo_status` `A (3)`, helper fallback snapshot function `B (7)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal service-helper extraction that preserves
public API behavior, SLO response fields, metric emission, safe-default behavior, and
operator-facing documentation truth.
