# CR-417: Reference Data Status Normalization Coverage

Date: 2026-05-28

## Scope

Query-service reference-data repository query-shape coverage for normalized source-data status
predicates.

## Finding

CR-416 normalized approved and active status predicates across effective-dated reference-data
source products, but the regression tests only locked the model portfolio and mandate subset. Client
restriction, sustainability preference, tax, income, liquidity, withdrawal, benchmark, and index
status predicates could regress back to raw persisted comparisons without focused test evidence.

## Change

Added query-shape coverage proving the remaining client source-data active gates use
`lower(trim(...)) = 'active'`. Added benchmark and index filter coverage proving caller-provided
status values are trimmed and lower-cased before comparison against normalized persisted statuses.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check tests/unit/services/query_service/repositories/test_reference_data_repository.py`

## Closure

Status: Hardened.

No production behavior, API route, OpenAPI, wiki source, or platform contract change was required.
This is a test-hardening slice that pins the reference-data query-boundary normalization introduced
by CR-416.
