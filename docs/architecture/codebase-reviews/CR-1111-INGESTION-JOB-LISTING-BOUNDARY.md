# CR-1111: Ingestion Job Listing Boundary

Date: 2026-06-20

## Scope

Move ingestion job-list read-model orchestration out of `ingestion_job_service.py` without
changing list filters, cursor semantics, response mapping, public service signatures, API
contracts, database schema, or operator-facing behavior.

## Finding

`IngestionJobService.list_jobs(...)` still owned cursor lookup, statement construction, page
loading, DTO mapping, and next-cursor extraction inline. The method was already low-complexity,
but it was the last non-trivial read-model branch in the public service facade and kept listing
persistence details outside the existing `ingestion_job_listing.py` boundary.

## Action

Added `load_job_list_response(...)` to `ingestion_job_listing.py` so the listing helper owns:

- optional cursor lookup
- filtered list-statement execution
- page construction and next-cursor selection
- row-to-response mapping through the existing lifecycle mapper

`IngestionJobService.list_jobs(...)` now constructs `IngestionJobListFilters` and delegates to the
helper with the repository session factory.

## Result

`ingestion_job_service.py` improved from `A (44.24)` / 522 SLOC to `A (48.85)` / 512 SLOC under
Radon. The expanded listing helper reports `A (43.44)` / 68 SLOC. `list_jobs(...)` is now
`A (1)`, and all service methods remain A-ranked by cyclomatic complexity.

## Evidence

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_job_listing.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py -q`
  => 22 passed
- `python -m pytest tests/unit/services/ingestion_service/services -q`
  => 80 passed
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_job_listing.py tests/unit/services/ingestion_service/services/test_ingestion_job_listing.py`
  => all checks passed
- `python -m ruff format --check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_job_listing.py tests/unit/services/ingestion_service/services/test_ingestion_job_listing.py`
  => 3 files already formatted
- `python -m radon mi -s src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_job_listing.py`
  => service `A (48.85)`, helper `A (43.44)`
- `python -m radon raw -s src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_job_listing.py`
  => service 512 SLOC, helper 68 SLOC
- `python -m radon cc -s src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_job_listing.py`
  => `list_jobs` reduced to `A (1)`; all service methods A-ranked

## Wiki Decision

No wiki source update is required. This is an internal read-model helper extraction that preserves
public ingestion API behavior, pagination semantics, OpenAPI contracts, database schema, and
operator-facing documentation truth.
