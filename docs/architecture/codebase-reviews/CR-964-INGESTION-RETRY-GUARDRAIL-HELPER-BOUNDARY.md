# CR-964: Ingestion Retry Guardrail Helper Boundary

Date: 2026-06-05

## Scope

Move deterministic ingestion retry guardrail checks into a reusable helper without changing replay
window semantics, paused-mode semantics, future-submission blocking, replay record-count limits,
backlog safety limits, error messages, or the public `assert_retry_allowed_for_records` service
method.

## Finding

`IngestionJobService.assert_retry_allowed_for_records` still mixed asynchronous service reads with
deterministic replay policy checks and error-message construction. After CR-963,
`ingestion_job_service.py` remained the last active non-generated C-ranked source hotspot.

## Action

Added `ingestion_retry_guardrails.py` with `assert_replay_guardrails`. The service method now owns
only asynchronous mode/backlog reads and delegates deterministic retry-policy enforcement to the
helper.

## Result

`IngestionJobService.assert_retry_allowed_for_records` improved from `B (9)` to `A (1)`.
The extracted helper module reports `A (59.19)` maintainability. `ingestion_job_service.py` shrank
from 1,207 SLOC to 1,200 SLOC and improved from `C (8.17)` to `B (9.82)`, clearing the active
non-generated C-ranked source hotspot list.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_capacity_status.py -q`
  => 20 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_retry_guardrails.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_retry_guardrails.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => 3 files already formatted
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_retry_guardrails.py`
  => `ingestion_job_service.py` 1,200 SLOC; `ingestion_retry_guardrails.py` 33 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_retry_guardrails.py -s`
  => `ingestion_job_service.py` `B (9.82)`; `ingestion_retry_guardrails.py` `A (59.19)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal service/helper extraction that preserves
public API contracts, retry guardrail semantics, and operator-facing documentation truth.
