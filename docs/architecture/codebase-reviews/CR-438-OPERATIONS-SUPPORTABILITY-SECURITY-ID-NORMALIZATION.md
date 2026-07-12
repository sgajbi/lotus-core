# CR-438: Operations Supportability Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service operations repository supportability queries for position lineage, valuation jobs,
reprocessing keys/jobs, and reconciliation findings.

## Finding

Several operations supportability paths filtered or joined by raw persisted `security_id` values.
Whitespace drift could hide a failed valuation job, reprocessing key, lineage artifact gap, or
blocking reconciliation finding from operator drilldowns even when the underlying calculation state
existed.

That is a reliability and supportability risk because banking operations teams need diagnostics to
surface the exact calculation or reconciliation evidence that explains a portfolio state.

## Change

Reused the shared query-service security identifier normalizer in operations supportability
queries. Required security lookups now fail closed for blank identifiers and compare against
trimmed persisted identifiers. Optional security filters for lineage keys, valuation jobs,
reprocessing keys/jobs, and reconciliation findings normalize padded requests and fail closed for
blank explicit filters. Lineage subqueries, superseding valuation-job checks, reprocessing payload
scope checks, and top blocking reconciliation-finding summaries now use canonical security
identifiers.

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
operational diagnostics hardening slice that prevents padded source identifiers from hiding
calculation, valuation, reprocessing, or reconciliation evidence from supportability views.
