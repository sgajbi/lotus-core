# CR-963: Ingestion Error Budget Status Helper Boundary

Date: 2026-06-05

## Scope

Move ingestion error-budget status query orchestration, pressure-ratio calculations, SQL failure
fallback, and response assembly into a dedicated helper module without changing response fields,
threshold defaults, pressure-ratio formulas, breach semantics, or the public
`IngestionJobService.get_error_budget_status` service method.

## Finding

`IngestionJobService.get_error_budget_status` mixed current/previous lookback SQL aggregates, DLQ
event counting, failure-rate calculation, backlog-growth calculation, replay/DLQ pressure
calculation, safe fallback behavior, and warning logging in one B-ranked service method.
`ingestion_job_service.py` remained the only active non-generated C-ranked source hotspot.

## Action

Added `ingestion_error_budget_status.py` with:

- `default_error_budget_status`
- `load_error_budget_status_response`

`IngestionJobService.get_error_budget_status` now delegates to the helper while passing runtime
policy thresholds, the service module's session factory, and the service logger. The existing
`_default_error_budget_status` service helper now delegates to the shared helper to preserve the
compatibility surface.

## Result

`IngestionJobService.get_error_budget_status` improved from `B (9)` to `A (1)`. The extracted
helper module reports `A (47.37)` maintainability. `ingestion_job_service.py` shrank from 1,304
SLOC to 1,207 SLOC and improved from `C (5.70)` to `C (8.17)`, but remains the remaining active
non-generated C-ranked source hotspot.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_capacity_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py -q`
  => 20 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_error_budget_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_error_budget_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => 3 files already formatted
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_error_budget_status.py`
  => `ingestion_job_service.py` 1,207 SLOC; `ingestion_error_budget_status.py` 139 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_error_budget_status.py -s`
  => `ingestion_job_service.py` `C (8.17)`; `ingestion_error_budget_status.py` `A (47.37)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal service/helper extraction that preserves
public API contracts, operational error-budget semantics, and operator-facing documentation truth.
