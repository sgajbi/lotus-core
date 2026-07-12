# CR-957: Ingestion Job Listing Helper Boundary

Date: 2026-06-05

## Scope

Move ingestion job listing filter construction, cursor lookup construction, and page cursor shaping
out of `ingestion_job_service.py` without changing list-job filters, descending job ordering,
cursor semantics, response DTO conversion, or router behavior.

## Finding

`IngestionJobService.list_jobs` mixed session iteration, optional filter construction, cursor row
lookup, cursor predicate application, ordering, limit+1 pagination, next-cursor calculation, and
DTO conversion. The method reported `C (11)` complexity and was the final C-ranked method in
`ingestion_job_service.py`.

## Action

Added `ingestion_job_listing.py` with:

- `IngestionJobListFilters`
- `IngestionJobListPage`
- `build_cursor_lookup_statement`
- `build_ingestion_job_list_statement`
- `ingestion_job_list_page`

`ingestion_job_service.py` now keeps ownership of database session access and DTO conversion while
delegating list-query policy and cursor page slicing to the helper module.

## Result

`list_jobs` improved from `C (11)` to `A (4)`, removing the final C-ranked method from
`ingestion_job_service.py`. The service reports `C (2.32)` maintainability, up from `C (0.81)`,
and remains a C-ranked module requiring additional B-ranked method/helper extraction. The new job
listing helper module reports `A (46.25)` maintainability.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_listing.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py -q`
  => 21 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_job_listing.py tests\unit\services\ingestion_service\services\test_ingestion_job_listing.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_job_listing.py tests\unit\services\ingestion_service\services\test_ingestion_job_listing.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py`
  => 4 files already formatted
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_job_listing.py`
  => `ingestion_job_service.py` 1,420 SLOC; listing helper 47 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_job_listing.py -s`
  => service `C (2.32)`, helper `A (46.25)`
- `python -m radon cc src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_job_listing.py -s`
  => `list_jobs` `A (4)`, helper statement builder `B (6)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal service-helper extraction that preserves
public API behavior, list-job filters, cursor semantics, and operator-facing documentation truth.
