# CR-471: Reconciliation FX Lookup Currency Normalization

Date: 2026-05-28

## Scope

Financial reconciliation FX-rate lookup used by authoritative timeseries integrity checks.

## Finding

`ReconciliationRepository.fetch_latest_fx_rate(...)` compared raw caller currency values directly
against persisted FX rows. If historical FX rows used lower-case or padded currency values,
reconciliation could treat an available rate as missing and then report false position/portfolio
timeseries mismatches.

For banking-grade controls, reconciliation must evaluate calculation evidence against the same
normalized reference-data semantics used by valuation and cost paths. A control should not fail
because of source formatting drift that the platform can safely normalize at the lookup boundary.

## Change

Updated the reconciliation repository so:

1. caller currencies use the shared `portfolio_common.currency_codes.normalize_currency_code(...)`
   helper,
2. persisted FX rows are compared through `upper(trim(...))` predicates compatible with the
   existing `ix_fx_rates_normalized_pair_rate_date` functional index,
3. repository tests prove padded lower-case input compiles to normalized predicates, preserves the
   as-of date fence, orders by latest rate date, and limits to one row.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py -q`
2. `python -m pytest tests/unit/services/financial_reconciliation_service -q`
3. `python -m ruff check src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py`
4. `python -m ruff format --check src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py`
5. `git diff --check`

Results:

1. Focused reconciliation repository proof: `3 passed`
2. Financial reconciliation unit pack: `18 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required.
Financial reconciliation now uses normalized, functional-index-compatible FX lookup semantics when
checking authoritative timeseries integrity.
