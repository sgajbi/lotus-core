# CR-413: Reconciliation Control Repository Status Normalization

Date: 2026-05-28

## Scope

Query-service operations repository reconciliation-run, reconciliation-finding, and portfolio-control
stage status handling.

## Finding

Reconciliation and portfolio-control supportability had service-level normalization for caller
filters and response classifiers, but repository predicates still compared persisted run status,
stage status, and finding severity values directly. Casing or whitespace drift could hide failed or
replay-required reconciliation runs from filtered operator views, mis-prioritize remediation work,
understate blocking finding totals, or place blocking control stages behind healthy rows.

## Change

Added repository-level normalization expressions using `upper(trim(...))` for reconciliation run
statuses, portfolio-control stage statuses, and reconciliation finding severity. Reused them for
reconciliation run count/list filters, reconciliation run priority ordering, finding severity
ranking and summary blocking counts, portfolio-control stage count/list filters, and
portfolio-control priority ordering. Updated operations repository query-shape tests to lock the
normalized predicates and ordering behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
operations repository reliability slice that keeps reconciliation and portfolio-control
supportability counts, filters, and operator ordering stable when persisted control codes drift.
