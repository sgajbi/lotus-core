# CR-1109: Ingestion SLO Status Boundary

Date: 2026-06-20

## Scope

Move ingestion SLO status orchestration out of `ingestion_job_service.py` without changing API
responses, threshold semantics, fallback behavior, logging event name, backlog-age metric updates,
or the public `IngestionJobService.get_slo_status` signature.

## Finding

`IngestionJobService.get_slo_status` still owned response timing, lookback-window calculation,
SQLAlchemy fallback handling, safe default response construction, backlog-age gauge updates, and
SLO response assembly while `ingestion_slo_status.py` already owned the SLO snapshot and response
mapping functions. The method was A-ranked, but the public service facade still mixed operational
diagnostic orchestration with persistence/read-model policy.

## Action

Expanded `ingestion_slo_status.py` with:

- `default_slo_status`
- `load_slo_status_response`

`IngestionJobService.get_slo_status` now delegates to the helper and passes the repository session
factory, backlog-age metric, and module logger into the helper. Existing service-level fallback
tests continue to prove the public method returns the same safe default when SLO queries are
unavailable, while helper tests continue to pin snapshot and threshold behavior.

## Result

`ingestion_job_service.py` improved from `A (38.41)` / 584 SLOC to `A (41.09)` / 550 SLOC under
Radon. The expanded SLO helper reports `A (39.95)` / 194 SLOC. The public service
`get_slo_status` method is now an A-ranked delegate, and the expanded helper remains within the
repo's enforced complexity gate.

## Evidence

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_slo_status.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py -q`
  => 21 passed
- `python -m pytest tests/unit/services/ingestion_service/services -q`
  => 79 passed
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_slo_status.py tests/unit/services/ingestion_service/services`
  => all checks passed
- `python -m ruff format --check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_slo_status.py tests/unit/services/ingestion_service/services`
  => 18 files already formatted
- `python -m radon mi -s src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_slo_status.py`
  => service `A (41.09)`, helper `A (39.95)`
- `python -m radon raw src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_slo_status.py`
  => service 550 SLOC, helper 194 SLOC
- `python -m radon cc -s -a src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_slo_status.py`
  => service methods A-ranked; helper average complexity `A (1.46)`

## Wiki Decision

No wiki source update is required. This is an internal service-helper extraction that preserves
public API behavior, metric contracts, logging posture, OpenAPI contracts, and operator-facing
documentation truth.
