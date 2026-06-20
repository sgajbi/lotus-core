# CR-1108: Ingestion Job Lifecycle Boundary

Date: 2026-06-20

## Scope

Move ingestion job creation, lifecycle state transitions, failure recording, simple job reads, and
failure listing out of `ingestion_job_service.py` without changing router contracts, API response
DTOs, database schema, metric names, metric labels, idempotency behavior, retry accounting, or
failure-row persistence semantics.

## Finding

`IngestionJobService` still owned the database-heavy core ingestion lifecycle inline after the
replay-audit split. That kept accepted-job creation, idempotency lookup, queued/failed/retried
state transitions, failure-observation recording, job replay-context reads, and failure listing in
the public service facade. The methods were already low-complexity, but the file remained the
current ingestion maintainability target and mixed facade orchestration with persistence details.

## Action

Added `ingestion_job_lifecycle.py` for:

- job and failure response mapping
- `IngestionJobCreateResult`
- `IngestionJobReplayContext`
- idempotent job creation
- queued, failed, and retried state transitions
- failure-observation persistence
- job read and replay-context read helpers
- failure listing

`IngestionJobService` keeps the same public method signatures while delegating lifecycle
persistence and metric side effects to the helper. Existing fake-session state-transition tests now
prove the behavior through the public facade against the extracted helper boundary.

## Result

`ingestion_job_service.py` improved from the last recorded `A (25.65)` / 726 SLOC to `A (38.41)` /
584 SLOC under Radon. The new lifecycle helper reports `A (40.28)` / 261 SLOC. All touched service
and helper functions remain A-ranked by cyclomatic complexity.

## Evidence

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_job_service_state_transitions.py -q`
  => 4 passed
- `python -m pytest tests/unit/services/ingestion_service/services -q`
  => 79 passed
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_job_lifecycle.py tests/unit/services/ingestion_service/services`
  => all checks passed
- `python -m ruff format --check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_job_lifecycle.py tests/unit/services/ingestion_service/services`
  => 18 files already formatted
- `python -m radon mi -s src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_job_lifecycle.py`
  => service `A (38.41)`, helper `A (40.28)`
- `python -m radon raw src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_job_lifecycle.py`
  => service 584 SLOC, helper 261 SLOC
- `python -m radon cc -s -a src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_job_lifecycle.py`
  => all touched service/helper functions A-ranked; average complexity `A (1.55)`

## Wiki Decision

No wiki source update is required. This is an internal service-helper extraction that preserves
public API behavior, metric contracts, retry/replay semantics, OpenAPI contracts, and
operator-facing documentation truth.
