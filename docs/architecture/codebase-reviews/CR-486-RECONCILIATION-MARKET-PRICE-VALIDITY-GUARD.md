# CR-486: Reconciliation Market Price Validity Guard

Date: 2026-05-28

## Scope

Financial reconciliation position-valuation reconstruction for stored daily position snapshots.

## Finding

Position valuation now rejects non-positive market prices before persisting valuation snapshots, but
financial reconciliation still trusted the stored snapshot `market_price` when reconstructing
expected market value and unrealized gain/loss. A dirty legacy snapshot or repair/replay mutation
with a zero or negative market price could cause reconciliation to derive expected values from an
invalid economic input rather than explicitly flagging the corrupted valuation basis.

For banking-grade reconciliation, invalid market-price evidence should be surfaced as a first-class
blocking finding. Reconciliation should not produce secondary expected-value arithmetic from a
known-invalid price.

## Change

Reused `portfolio_common.market_prices.coerce_positive_market_price_or_none(...)` in
`ReconciliationService.run_position_valuation(...)`.

The position-valuation reconciliation path now:

1. validates stored snapshot `market_price` before expected market-value reconstruction,
2. records an `invalid_market_price` error finding for missing, invalid, zero, or negative prices,
3. reports expected market-price posture as `>0`,
4. skips derived market-value and unrealized-gain/loss arithmetic for the invalid row.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py -q`
2. `python -m pytest tests/unit/services/financial_reconciliation_service -q`
3. `python -m pytest tests/unit/services/calculators/position_valuation_calculator tests/unit/libs/portfolio-common/test_market_prices.py tests/unit/libs/portfolio-common/test_valuation_prices.py tests/unit/services/financial_reconciliation_service -q`
4. `python -m ruff check src/services/financial_reconciliation_service/app/services/reconciliation_service.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
5. `python -m ruff format --check src/services/financial_reconciliation_service/app/services/reconciliation_service.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
6. `make warning-gate`
7. `git diff --check`

Results:

1. Focused reconciliation proof: `11 passed`
2. Financial reconciliation unit pack: `20 passed`
3. Affected valuation, market-price, valuation-price, and reconciliation packs: `65 passed`
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Warning gate: `2348 passed`, `9 deselected`, zero warnings
7. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
financial reconciliation service now catches invalid stored market-price evidence directly instead
of allowing corrupted prices to become the basis for reconstructed valuation math.
