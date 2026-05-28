# CR-406: Operations Terminal Failure Status Normalization

Date: 2026-05-28

## Scope

Query-service operations support-job and reconciliation-run terminal failure metadata.

## Finding

Operations records already normalized status values for retry, stale, blocking, and
operational-state classification, but selected terminal-failure flags still compared raw status
values to `FAILED`. Padded valid values such as ` failed ` could therefore emit a failed
operational state while incorrectly reporting `is_terminal_failure=false`.

## Change

Added a shared operations terminal-failure predicate backed by the existing trim-plus-uppercase
status normalizer. Routed support-job and reconciliation-run terminal-failure metadata through the
shared predicate. Added direct operations-service tests proving padded lower-case failure statuses
remain terminal failures while preserving the raw persisted status in returned records.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_operations_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an internal
operations supportability metadata consistency slice.
