# CR-965: Ingestion Reprocessing Queue Health Helper Boundary

Date: 2026-06-05

## Scope

Move reprocessing queue-health SQL aggregation, row normalization, queue ordering, and response
assembly into a dedicated helper module without changing response fields, grouping behavior,
oldest-pending age calculation, total counts, or the public
`IngestionJobService.get_reprocessing_queue_health` service method.

## Finding

`IngestionJobService.get_reprocessing_queue_health` mixed database aggregation, mapped-row
normalization, per-queue age calculation, total count accumulation, queue ordering, and response
assembly in one B-ranked service method. The method is operationally important because it feeds
operator visibility into reprocessing backlog pressure.

## Action

Added `ingestion_reprocessing_queue_health.py` with `load_reprocessing_queue_health_response`.
The service method now delegates to that helper while passing the service module's session factory,
preserving the existing test monkeypatch seam and public service shape.

## Result

`IngestionJobService.get_reprocessing_queue_health` improved from `B (7)` to `A (1)`. The
extracted helper module reports `A (51.01)` maintainability. `ingestion_job_service.py` shrank
from 1,200 SLOC to 1,137 SLOC and improved from `B (9.82)` to `B (11.79)`.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py -q`
  => 18 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_reprocessing_queue_health.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_reprocessing_queue_health.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => passed after formatting touched files
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_reprocessing_queue_health.py`
  => `ingestion_job_service.py` 1,137 SLOC; `ingestion_reprocessing_queue_health.py` 78 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_reprocessing_queue_health.py -s`
  => `ingestion_job_service.py` `B (11.79)`; `ingestion_reprocessing_queue_health.py` `A (51.01)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal service/helper extraction that preserves
public API contracts, reprocessing queue-health semantics, and operator-facing documentation truth.
