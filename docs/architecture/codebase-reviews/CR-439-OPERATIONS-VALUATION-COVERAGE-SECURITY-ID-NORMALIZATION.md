# CR-439: Operations Valuation Coverage Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service operations repository valuation coverage and snapshot/history supportability checks.

## Finding

Valuation coverage and snapshot/history mismatch checks joined `daily_position_snapshots`,
`position_history`, and `position_state` by raw persisted `security_id` values. Whitespace drift
could falsely report missing snapshots, understate valuation coverage, or inflate artifact-gap
counts even when the calculation artifacts existed for the same canonical security.

That is a calculation readiness risk because these operations surfaces help determine whether
valuation, snapshot, and timeseries materialization are complete enough for banking operations.

## Change

Reused the operations repository security identifier expression for valuation coverage joins.
Latest-snapshot-date checks, as-of snapshot checks, snapshot/history mismatch subqueries, and
snapshot valuation coverage now join and group by trimmed security identifiers while preserving
portfolio and epoch constraints.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `python -m pytest tests/unit/services/query_service/services -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an
operations-readiness hardening slice that prevents padded source identifiers from creating false
valuation coverage or snapshot/history artifact-gap evidence.
