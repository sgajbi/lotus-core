# CR-932: Core Snapshot Instrument Enrichment Boundary

Date: 2026-06-04

## Scope

Move core snapshot instrument-enrichment request normalization, returned-instrument lookup mapping,
and DTO record shaping out of `CoreSnapshotService` without changing repository access,
request-validation errors, record ordering, unknown-security behavior, API contracts, metrics, or
database schema.

## Finding

`CoreSnapshotService` still owned pure instrument-enrichment helper logic inline even though the
service method only needs to validate the request, read instruments from the repository, and return
records in request order. Keeping these pure helpers in the service widened a C-ranked
maintainability hotspot and made the enrichment DTO boundary less reusable.

## Action

Extracted `core_snapshot_instrument_enrichment.py` with helpers for:

- requested security-id normalization,
- returned instrument lookup-map construction,
- ordered enrichment record construction,
- unknown security fallback records.

The service keeps the public request validation error and repository call, then delegates response
assembly to the helper.

## Result

`core_snapshot_service.py` shrank from 1,093 SLOC to 1,067 SLOC. The new
`core_snapshot_instrument_enrichment.py` module reports `A (64.32)` under Radon maintainability,
with no B-or-worse complexity findings in the scoped service/helper check output. The active
service remains a C-ranked maintainability hotspot, so follow-up core-snapshot extraction remains
valuable.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_instrument_enrichment.py tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 47 passed
- `python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_instrument_enrichment.py tests\unit\services\query_service\services\test_core_snapshot_instrument_enrichment.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_instrument_enrichment.py tests\unit\services\query_service\services\test_core_snapshot_instrument_enrichment.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_instrument_enrichment.py`
  => `core_snapshot_service.py` 1,067 SLOC; `core_snapshot_instrument_enrichment.py` 40 SLOC
- `python -m radon mi src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_instrument_enrichment.py -s`
  => service `C (0.00)`, helper `A (64.32)`
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_instrument_enrichment.py -s`
  => no B-or-worse complexity findings in the scoped service/helper check output

## Wiki Decision

No wiki source update is required. This is an internal core snapshot service extraction that
preserves API contracts, request-validation behavior, record ordering, unknown-security behavior,
operator workflows, and public documentation truth.
