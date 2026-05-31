# CR-571: Client Source-Data SQL Ranking Completion

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

After CR-569, client restriction and sustainability preference reads selected latest effective
business rows in SQL, but the remaining client source-data products still fetched superseded rows
and deduplicated in Python:

1. `ClientTaxProfile:v1`
2. `ClientTaxRuleSet:v1`
3. `ClientIncomeNeedsSchedule:v1`
4. `LiquidityReserveRequirement:v1`
5. `PlannedWithdrawalSchedule:v1`

These reads are part of the DPM source-data evidence family used by `lotus-manage` supportability
and downstream workflow checks. Materializing superseded client facts is avoidable read
amplification on high-volume client books.

## Change

Routed the five remaining client evidence reads through the shared
`_ranked_latest_effective_ids(...)` SQL helper.

The ranking now happens inside the database with `row_number()` partitioned by each product's
business key:

1. tax profile id,
2. tax rule set, jurisdiction, and rule code,
3. income-needs schedule id,
4. liquidity reserve requirement id,
5. planned withdrawal schedule id and scheduled date.

The query predicates, active-status defaults, optional mandate scoping, date windows, and final
response ordering are preserved.

## Impact

Client DPM source-data reads no longer ask Python to discard superseded tax, income, liquidity, or
withdrawal rows after the database has already returned them. This keeps the implementation aligned
with the active partial indexes added earlier on this branch and completes the client source-data
SQL-ranking pass without changing API route shape, response DTOs, database schema, or platform
contracts.

Repo-local wiki source was updated to keep the supported-features page aligned with the current
implementation. Wiki publication must wait until after this branch is merged to `main`.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q` - 27 passed
2. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q` - 99 passed
3. `python -m alembic heads` - `c0fcd4e5f6a7 (head)`
4. `python scripts/migration_contract_check.py --mode alembic-sql` - passed
5. touched-surface `python -m ruff check` - passed
6. touched-surface `python -m ruff format --check` - passed
7. `git diff --check` - passed
8. `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` - expected unmerged-branch published wiki drift for `_Sidebar.md`, `Database-Migrations.md`, `Home.md`, and `Supported-Features.md`
