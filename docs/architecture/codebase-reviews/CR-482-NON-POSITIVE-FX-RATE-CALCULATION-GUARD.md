# CR-482: Non-Positive FX Rate Calculation Guard

Date: 2026-05-28

## Scope

FX-rate positivity handling across valuation, portfolio timeseries aggregation, and financial
reconciliation calculation paths.

## Finding

The valuation calculator already failed closed when a required FX rate was zero or negative, but
portfolio timeseries aggregation and financial reconciliation aggregate reconstruction did not share
that policy. A historical or manually inserted negative FX row could therefore invert portfolio
market value, cashflow, and fee aggregation during institutional calculation or reconciliation
proof.

For banking-grade calculations, non-positive FX rates must never participate in portfolio-value
math. The authoritative ingestion and event boundaries reject non-positive rates, but downstream
calculation logic still needs a defensive read-side guard for dirty historical rows, repair mistakes,
manual database edits, and replay/reconciliation paths.

## Change

Added `portfolio_common.fx_rates.coerce_positive_fx_rate_or_none(...)` and reused it in:

1. `ValuationLogic._positive_fx_rate_or_none(...)`,
2. `PortfolioTimeseriesLogic._resolve_fx_rate(...)`,
3. `ReconciliationService._aggregate_authoritative_portfolio_metrics(...)`.

Portfolio timeseries aggregation now raises `FxRateNotFoundError` for a non-positive required FX
rate instead of multiplying values by it. Financial reconciliation now treats non-positive FX rates
like unavailable conversion evidence and skips that foreign-currency contribution rather than
allowing a negative or zero rate to distort reconstructed authoritative totals.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_fx_rates.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_portfolio_timeseries_logic.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common tests/unit/services/calculators/position_valuation_calculator tests/unit/services/timeseries_generator_service/timeseries-generator-service tests/unit/services/financial_reconciliation_service -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/fx_rates.py src/services/calculators/position_valuation_calculator/app/logic/valuation_logic.py src/services/timeseries_generator_service/app/core/portfolio_timeseries_logic.py src/services/financial_reconciliation_service/app/services/reconciliation_service.py tests/unit/libs/portfolio-common/test_fx_rates.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_portfolio_timeseries_logic.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
4. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/fx_rates.py src/services/calculators/position_valuation_calculator/app/logic/valuation_logic.py src/services/timeseries_generator_service/app/core/portfolio_timeseries_logic.py src/services/financial_reconciliation_service/app/services/reconciliation_service.py tests/unit/libs/portfolio-common/test_fx_rates.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_portfolio_timeseries_logic.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
5. `make warning-gate`
6. `git diff --check`

Results:

1. Focused FX-rate calculation proof: `33 passed`
2. Affected unit packs: `598 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Warning gate: `2340 passed`, `9 deselected`, zero warnings
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
read-side calculation guard now aligns portfolio timeseries and reconciliation behavior with the
existing valuation fail-closed FX-rate policy.
