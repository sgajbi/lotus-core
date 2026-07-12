# CR-953: Ingestion Record Status Helper Boundary

Date: 2026-06-05

## Scope

Move ingestion job record-status parsing policy out of `ingestion_job_service.py` without changing
database access, response shape, endpoint behavior, retry/replay semantics, or router contracts.

## Finding

`IngestionJobService.get_job_record_status` mixed database lookup, failure-history retrieval,
failed-record-key normalization, endpoint-specific replayable-key extraction, and response assembly
in one method. The method reported `C (20)` complexity, making the ingestion operations service
harder to review and reason about.

## Action

Added `ingestion_record_status.py` with:

- `failed_record_keys_from_failures`
- `replayable_record_keys_from_payload`
- `REPLAYABLE_RECORD_KEY_FIELDS`

`IngestionJobService.get_job_record_status` now keeps ownership of database reads and response
construction while delegating pure record-status parsing to the helper module.

## Result

`get_job_record_status` improved from `C (20)` to `A (4)`. `ingestion_job_service.py` shrank from
1,656 SLOC to 1,633 SLOC and remains `C (0.00)` under Radon maintainability, requiring additional
focused extractions. The new helper module reports `A (59.21)` maintainability, with helper
complexity at `B (6)` for endpoint mapping and `A (5)` for failed-key normalization.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_record_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py -q`
  => 21 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_record_status.py tests\unit\services\ingestion_service\services\test_ingestion_record_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_record_status.py tests\unit\services\ingestion_service\services\test_ingestion_record_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => 4 files already formatted
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_record_status.py`
  => `ingestion_job_service.py` 1,633 SLOC; record-status helper 31 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_record_status.py -s`
  => service `C (0.00)`, helper `A (59.21)`
- `python -m radon cc src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_record_status.py -s`
  => `get_job_record_status` `A (4)`, helper functions `B (6)` / `A (5)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal service-helper extraction that preserves
public API behavior, OpenAPI contracts, retry/replay semantics, and operator-facing documentation
truth.
