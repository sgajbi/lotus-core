# CR-969: Ingestion Idempotency Diagnostics Helper Boundary

Date: 2026-06-05

## Scope

Move idempotency diagnostics aggregate loading, endpoint normalization, collision detection, and
response assembly into a dedicated helper module without changing public service behavior, endpoint
response fields, lookback filtering, usage ordering, or collision semantics.

## Finding

`IngestionJobService.get_idempotency_diagnostics` mixed aggregate SQL construction, idempotency-key
row normalization, endpoint sorting, collision counting, and DTO assembly in one B-ranked service
method. It was the final B-ranked method left in `ingestion_job_service.py` after CR-968.

## Action

Added `ingestion_idempotency_diagnostics.py` with `load_idempotency_diagnostics_response` and a
private row-to-item mapper. The service method now delegates to the helper while passing the
service module's session factory, preserving the existing test monkeypatch seam and public method
contract.

## Result

`IngestionJobService.get_idempotency_diagnostics` improved from `B (7)` to `A (1)`. The extracted
helper module reports `A (59.15)` maintainability. `ingestion_job_service.py` shrank from 1,045
SLOC to 990 SLOC and improved from `B (15.15)` to `B (16.96)`. The service now has no B-ranked
methods under Radon cyclomatic complexity.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py -q`
  => 18 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_idempotency_diagnostics.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_idempotency_diagnostics.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => passed after formatting touched files
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_idempotency_diagnostics.py`
  => `ingestion_job_service.py` 990 SLOC; `ingestion_idempotency_diagnostics.py` 86 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_idempotency_diagnostics.py -s`
  => `ingestion_job_service.py` `B (16.96)`; `ingestion_idempotency_diagnostics.py` `A (59.15)`
- `python -m radon cc src\services\ingestion_service\app\services\ingestion_job_service.py -s | Select-String -Pattern " - [BCDEF]"`
  => no B/C/D/E/F service methods reported
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal idempotency diagnostics helper extraction
that preserves public API contracts, diagnostic semantics, and operator-facing documentation truth.
