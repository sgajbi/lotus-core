# CR-516: Partition Advisor Market Reference Series Coverage

Date: 2026-05-29

## Scope

Partition automation coverage for high-volume date-ranged market and reference series.

## Finding

`scripts/db_partition_advisor.py` already provides the right conservative automation pattern for
partition planning: generate monthly range-partition DDL and execute it only for tables that are
already PostgreSQL partitioned parents. That avoids unsafe in-place conversion of populated tables.

The candidate list covered core transaction, position, snapshot, cashflow, and market-price fact
tables, but it omitted adjacent market/reference series that feed performance, risk, reporting, and
valuation workflows:

1. `fx_rates`
2. `index_price_series`
3. `index_return_series`
4. `benchmark_return_series`
5. `risk_free_series`

These tables are naturally date-ranged and can grow materially as historical analytics windows
expand.

## Change

1. Added `fx_rates` with monthly `rate_date` partition recommendation.
2. Added `index_price_series`, `index_return_series`, `benchmark_return_series`, and
   `risk_free_series` with monthly `series_date` partition recommendation.
3. Added unit proof that the partition advisor covers the market/reference series tables with the
   correct partition key.

## Evidence

Commands:

1. `python -m pytest tests/unit/scripts/test_db_partition_advisor.py -q`
2. `python -m ruff check scripts/db_partition_advisor.py tests/unit/scripts/test_db_partition_advisor.py`
3. `python -m ruff format --check scripts/db_partition_advisor.py tests/unit/scripts/test_db_partition_advisor.py`
4. `git diff --check`

Results:

1. Passed: 4 tests.
2. Passed.
3. Passed.
4. Passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
extends existing governed partition planning automation without attempting unsafe table conversion.
