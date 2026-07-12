# CR-692: Cashflow Evidence Window Helper

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`CashflowProjectionService` and `PortfolioLiquidityLadderService` both carried local
booked/projected cashflow evidence read branching, including the same latest-evidence timestamp
merge policy. That duplicated source-data evidence assembly behavior across two portfolio cashflow
products and made future changes to booked-only or projected evidence semantics harder to keep
aligned.

## Change

Added `read_cashflow_evidence_window(...)` and `CashflowEvidenceWindow` to centralize booked
cashflow evidence reads, optional projected settlement cashflow reads, concurrent projected-window
execution, and latest-evidence timestamp resolution.

`PortfolioCashflowProjection` now consumes the shared helper directly. `PortfolioLiquidityLadder`
continues to run snapshot rows and cashflow evidence reads concurrently, but the cashflow portion is
delegated to the shared helper.

Added focused helper coverage proving booked and projected evidence reads start concurrently and
booked-only reads skip projected evidence.

## Impact

This reduces duplicated source-data cashflow evidence assembly while preserving
`PortfolioCashflowProjection` and `PortfolioLiquidityLadder` response shape, booked-only behavior,
projected settlement behavior, latest evidence metadata, source-batch fingerprint semantics,
database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused cashflow evidence helper, cashflow projection, and liquidity ladder proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
