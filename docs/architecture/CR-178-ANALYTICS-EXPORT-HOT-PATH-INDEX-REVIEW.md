# CR-178 Analytics Export Hot Path Index Review

## Finding
Analytics export is now exposed as a first-class durable queue on the support API, but the underlying table still had only single-column indexes. The reviewed queue scans and support queries filter by `portfolio_id`, `status`, `created_at`, and `updated_at`, so the queue shape had fallen behind the other hardened control queues.

## Change
- Added ORM metadata indexes for analytics export queue hot paths.
- Added an Alembic migration for:
  - `(portfolio_id, status, created_at)`
  - `(status, updated_at)`
- Added metadata-level proof in `tests/unit/libs/portfolio-common/test_database_models.py`.

## Why It Matters
Analytics export is an operational queue, not just a result table. Queue-pressure visibility without matching queue-path indexing leaves the control plane honest but slower under load.

## Evidence
- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `alembic/versions/f6a7b8c9d0e1_perf_add_analytics_export_hot_path_indexes.py`
- `tests/unit/libs/portfolio-common/test_database_models.py`
