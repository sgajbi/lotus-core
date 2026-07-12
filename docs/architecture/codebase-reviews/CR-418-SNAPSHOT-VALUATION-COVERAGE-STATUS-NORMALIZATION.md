# CR-418: Snapshot Valuation Coverage Status Normalization

Date: 2026-05-28

## Scope

Query-service operations repository snapshot valuation coverage summary.

## Finding

`get_snapshot_valuation_coverage_summary(...)` counted valued positions with a raw
`DailyPositionSnapshot.valuation_status != "UNVALUED"` predicate. Padded or case-varied unvalued
statuses could be counted as valued positions, overstating snapshot valuation coverage and
weakening downstream readiness, reporting, and supportability evidence.

## Change

Added a repository-level snapshot valuation-status expression using `upper(trim(...))` and reused it
for the valued-position predicate. Updated the operations repository query-shape test to lock the
normalized predicate.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
operations repository correctness slice that keeps valuation coverage evidence stable when
persisted snapshot valuation status control codes drift.
