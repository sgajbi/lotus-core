# CR-595: Snapshot Evidence Timestamp Helper

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Cash balance, reporting, and liquidity ladder services carried duplicate logic for deriving the
latest snapshot evidence timestamp from `updated_at` and `created_at` fields. These timestamps feed
source-data product lineage and operational freshness metadata, so duplicated aggregation logic can
cause drift in audit evidence across API read paths.

## Change

Added `snapshot_evidence.py` with a tested `latest_snapshot_evidence_timestamp(...)` helper and
routed cash balance and liquidity ladder source-data metadata through it. Removed the duplicate
reporting-service static helper and moved its coverage to the shared helper.

## Impact

This centralizes snapshot lineage timestamp aggregation for source-data product responses and
keeps audit/freshness behavior directly tested. API route shape, response fields, OpenAPI
contracts, database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal lineage-helper reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_snapshot_evidence.py tests/unit/services/query_service/services/test_cash_balance_service.py tests/unit/services/query_service/services/test_liquidity_ladder_service.py tests/unit/services/query_service/services/test_reporting_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
