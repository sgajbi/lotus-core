# CR-192 Lineage Key Support Artifact Visibility Review

## Finding

`GET /lineage/portfolios/{portfolio_id}/keys` only exposed epoch, watermark, and replay status. Operators still had to pivot into per-key lineage or direct database inspection to understand whether the current epoch had recent position history, daily snapshots, or valuation jobs.

## Change

- Enriched `LineageKeyRecord` with current-epoch artifact truth:
  - `latest_position_history_date`
  - `latest_daily_snapshot_date`
  - `latest_valuation_job_date`
  - `latest_valuation_job_status`
- Folded those values into the existing repository query with correlated subqueries so the listing remains one durable support-plane path.
- Added unit, router, and OpenAPI proof.

## Why it matters

The support-plane listing is now operationally useful on its own. Operators can see whether a key is lagging because of replay state, missing snapshots, or valuation job status without leaving the listing contract.

## Evidence

- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
