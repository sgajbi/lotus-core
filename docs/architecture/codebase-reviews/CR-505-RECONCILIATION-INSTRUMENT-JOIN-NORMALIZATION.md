# CR-505: Reconciliation Instrument Join Normalization

Date: 2026-05-29

## Scope

Financial reconciliation reads that enrich position valuation and authoritative position time-series
rows with instrument reference data.

## Finding

The financial reconciliation repository still joined `instruments` to `daily_position_snapshots`
and `position_timeseries` through raw `security_id` equality. That was inconsistent with the
normalized security-id predicates used by the query service and calculation repositories, and it
did not take advantage of the normalized instrument lookup index added in CR-504.

For bank-scale reconciliation runs, the raw join shape also made identifier whitespace drift a
correctness risk: a position row with a padded security identifier could be omitted from
reconciliation enrichment even when the canonical instrument row existed.

## Change

Updated reconciliation repository query shapes so instrument enrichment joins use normalized
security identifiers:

1. `fetch_position_valuation_rows(...)` now joins
   `trim(instruments.security_id)` to `trim(daily_position_snapshots.security_id)`.
2. `fetch_authoritative_position_timeseries_rows(...)` now joins
   `trim(instruments.security_id)` to `trim(position_timeseries.security_id)`.

Added focused unit tests that compile and assert both SQL join shapes, preserving the existing
portfolio, business-date, epoch, and deterministic ordering predicates.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py -q`
2. `python -m pytest tests/unit/services/financial_reconciliation_service -q`
3. `python -m pytest tests/integration/services/financial_reconciliation_service -q`
4. `python -m ruff check src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py`
5. `python -m ruff format --check src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py`
6. `git diff --check`

Results:

1. Focused reconciliation repository proof: `6 passed`
2. Financial reconciliation unit pack: `23 passed`
3. Financial reconciliation integration pack: `12 passed`
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, database migration, wiki source, or platform contract change was required.
This slice aligns reconciliation enrichment reads with the normalized identifier convention and
the existing CR-504 functional index.
