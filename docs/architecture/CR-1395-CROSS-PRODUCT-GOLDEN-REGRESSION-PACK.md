# CR-1395 Cross-Product Golden Regression Pack

## Objective

Progress GitHub issue #607 by creating a governed reusable golden regression pack for transaction
lifecycle and corporate-action examples across product families.

## Finding

Core already had BUY/SELL/DIVIDEND/INTEREST/FX characterization tests, CA bundle A validation and
reconciliation tests, portfolio-flow bundle tests, and selected E2E coverage. The evidence was
fragmented and there was no reusable fixture that made expected position, cash, cost, income, and
lineage impact visible across product families.

## Actions

- Added `tests/fixtures/cross-product-transaction-golden-scenarios.v1.json` with synthetic golden
  examples and explicit expected sections for position state, cash ledger impact, cost basis impact,
  income/cashflow impact, and lineage.
- Added `docs/standards/cross-product-golden-regression-pack.v1.json` to define required scenario
  coverage, statuses, executable evidence, and sensitive-data policy.
- Added `scripts/cross_product_golden_regression_guard.py` plus focused guard tests.
- Added executable unit-level golden tests for equity buy/sell cost relief, dividend income,
  transfer in/out position and cost deltas, and CA bundle spin-off basis transfer.
- Wired `make cross-product-golden-regression-guard` into lint and updated testing strategy, risk
  matrix, repo context, wiki source, and this review ledger.

## Compatibility

No runtime behavior, API route, DTO/OpenAPI schema, database schema, Kafka topic, event payload, or
deployment topology changed. This slice adds reusable fixtures, executable tests, and governance.

The pack remains honest about product families that still need deeper executable coverage:
fund subscription/redemption/distribution/reinvestment, option exercise/expiry, structured-product
coupon/barrier/payoff, and full correction/cancel/rebook/restatement. Those gaps remain visible in
#607 until follow-up implementation issues are split or the examples become executable.

## Validation

Run before commit:

- `python -m pytest tests/unit/scripts/test_cross_product_golden_regression_guard.py -q`
- `python scripts/cross_product_golden_regression_guard.py`
- `python -m pytest tests/unit/transaction_specs/test_cross_product_golden_scenarios.py -q`
- scoped Ruff lint and format over the new guard/tests
- `make cross-product-golden-regression-guard`
- `make risk-based-test-coverage-matrix-guard`
- `make quality-wiki-docs-gate`
- `make lint`
- `git diff --check`

## Guidance Decision

Repo-local context, testing strategy, risk matrix, and wiki source changed because golden regression
fixtures are durable Core test truth. No platform skill change is required for this slice; the
existing backend delivery and issue-loop skills already require issue-derived patterns to become
repo-native guards and context when repeatable.
