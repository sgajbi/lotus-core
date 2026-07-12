# CR-956: Ingestion Backlog Breakdown Helper Boundary

Date: 2026-06-05

## Scope

Move ingestion backlog breakdown row normalization, ordering, concentration-share calculation, and
response assembly out of `ingestion_job_service.py` without changing database access, grouping
query semantics, response shape, or backlog concentration behavior.

## Finding

`IngestionJobService.get_backlog_breakdown` mixed session iteration, total backlog count retrieval,
grouped query execution, row normalization, backlog-age calculation, failure-rate calculation,
ordering, limiting, concentration-share calculation, and response assembly. The method reported
`C (13)` complexity and kept backlog concentration policy coupled to the broad ingestion service.

## Action

Added `ingestion_backlog_breakdown.py` with:

- `build_backlog_breakdown_response`
- `backlog_breakdown_item_from_row`
- `empty_backlog_breakdown_response`

`ingestion_job_service.py` now keeps ownership of database reads and query predicates while
delegating pure backlog response shaping to the helper module.

## Result

`get_backlog_breakdown` improved from `C (13)` to `A (3)`. `ingestion_job_service.py` shrank from
1,477 SLOC to 1,419 SLOC and improved from `C (0.00)` to `C (0.81)` under Radon maintainability.
The service remains a C-ranked hotspot, with `list_jobs` now the remaining C-ranked service method.
The new backlog helper module reports `A (51.73)` maintainability.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_backlog_breakdown.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_backlog_breakdown.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py -q`
  => 19 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_backlog_breakdown.py tests\unit\services\ingestion_service\services\test_ingestion_backlog_breakdown.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_backlog_breakdown.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_backlog_breakdown.py tests\unit\services\ingestion_service\services\test_ingestion_backlog_breakdown.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_backlog_breakdown.py`
  => 4 files already formatted
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_backlog_breakdown.py`
  => `ingestion_job_service.py` 1,419 SLOC; backlog helper 98 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_backlog_breakdown.py -s`
  => service `C (0.81)`, helper `A (51.73)`
- `python -m radon cc src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_backlog_breakdown.py -s`
  => `get_backlog_breakdown` `A (3)`, helper row normalizer `B (6)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal service-helper extraction that preserves
public API behavior, backlog response fields, query semantics, and operator-facing documentation
truth.
