# CR-402: Analytics Export Status Normalization

Date: 2026-05-28

## Scope

Query-service operations analytics export status classification.

## Finding

Analytics export status normalization lowercased status values without trimming. Padded valid values
such as ` FAILED ` or ` accepted ` could miss the intended operational-state branch. In the failed
case, that could incorrectly classify a failed analytics export as `COMPLETED`, weakening
operations health, failed-job counts, and supportability triage.

## Change

Trimmed status before lowercasing in `_normalize_analytics_export_status(...)`. Updated branch
coverage so padded failed and accepted statuses still classify as `FAILED` and `ACCEPTED`.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_operations_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an operations
supportability and failed-job classification correctness slice.
