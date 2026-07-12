# CR-187 - Support Listing Operational Priority Ordering Review

Date: 2026-03-13

## Problem

The support-plane listing endpoints were still ordered mainly by recency:

- valuation jobs by `valuation_date DESC`
- aggregation jobs by `aggregation_date DESC`
- analytics export jobs by `created_at DESC`
- reconciliation runs by `started_at DESC`

That is weak for incident response. Operators need blocking, failed, and stale work first, not merely the newest rows.

## Change

Moved the ordering contract into the durable repository queries so paging reflects operational priority:

- failed rows first
- then stale in-flight rows
- then active in-flight rows
- then pending/accepted rows
- then the remaining rows

Within each priority band:

- valuation and aggregation jobs sort by oldest business date first
- analytics export jobs sort by oldest created job first
- reconciliation runs sort blocking statuses first, then newest start time

## Why this is better

- Support listings now align with operator triage instead of database recency.
- Paging is truthful because prioritization happens before `OFFSET/LIMIT`.
- The ordering rule is centralized in the repository layer instead of duplicated in clients.

## Evidence

- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
