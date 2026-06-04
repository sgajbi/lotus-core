# CR-903: Core Snapshot Instrument Enrichment Boundary

Date: 2026-06-04

## Scope

Reduce `CoreSnapshotService` instrument-enrichment complexity without changing public service
methods, request identifier trimming, repository lookup behavior, result ordering, unknown-security
handling, issuer metadata mapping, or response DTOs.

## Finding

`CoreSnapshotService.get_instrument_enrichment_bulk` was a C-ranked method mixing request
normalization, empty-request validation, repository lookup, returned security-id normalization,
lookup map construction, order preservation, unknown-security fallback, and DTO construction.

## Action

Extracted focused helpers:

- `_requested_instrument_security_ids`
- `_instrument_enrichment_map`
- `_instrument_enrichment_record`

## Result

`get_instrument_enrichment_bulk` now reports `A (2)` instead of `C (13)` under Radon cyclomatic
complexity. The extracted instrument-enrichment helpers report A-ranked complexity.
`core_snapshot_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot count
remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => 44 passed
- `python -m ruff format src\services\query_service\app\services\core_snapshot_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py -s`
  => `get_instrument_enrichment_bulk - A (2)`; extracted instrument-enrichment helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.
