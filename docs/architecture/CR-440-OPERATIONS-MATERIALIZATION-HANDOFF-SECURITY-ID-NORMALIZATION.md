# CR-440: Operations Materialization Handoff Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service operations repository load-run progress and health-summary supportability surfaces.

## Finding

Materialization handoff latency joined completed valuation jobs to position-timeseries rows using
raw `security_id` values. Reprocessing and valuation health summaries also emitted oldest-key/job
security identifiers directly from persisted rows. Whitespace drift could overstate completed
valuation jobs waiting for position timeseries, understate latency sample coverage, or surface
non-canonical security identifiers in operator health evidence.

That is an operational readiness risk because these metrics guide whether a load run has completed
calculation materialization and where operators should investigate.

## Change

Reused the operations repository security identifier expression in load-run handoff queries and
health summaries. Completed valuation handoff rows now expose canonical security identifiers and
join position timeseries through trimmed identifiers. Reprocessing and valuation health summaries
select canonical identifiers and normalize returned oldest-key/job security IDs.

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
operations-readiness hardening slice that prevents padded source identifiers from distorting
load-run materialization handoff evidence or health-summary security identity.
