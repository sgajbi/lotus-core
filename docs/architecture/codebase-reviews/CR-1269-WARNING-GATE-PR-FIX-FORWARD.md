# CR-1269 Warning Gate PR Fix-Forward

Date: 2026-07-01

## Objective

Fix the PR #695 Feature Lane and PR Merge Gate `warning-gate` failures without weakening the
warning budget, unit test coverage, structured logging, or query read-model contracts.

## Change

- Updated Kafka producer delivery callback tests to assert the current structured log contract
  instead of legacy free-form message strings.
- Added the required `traceparent` field to the outbox dispatcher claimed-event fixture.
- Aligned the query integration test repository fixture with the `BuyStateRepository` port by
  returning `PortfolioTaxLotReadRecord` objects instead of raw `(lot, currency)` tuples.
- Made transaction raw-landing diagnostic log assertions explicit about the transaction consumer
  logger so the full unit suite is deterministic after logging setup changes in earlier tests.

## Validation Evidence

- Exact GitHub-failing set: 7 passed.
- Affected persistence/logging/query set: 8 passed.
- `make warning-gate`: 3414 passed, 10 deselected, zero warnings.
- Scoped Ruff lint on touched tests: passed.
- Scoped Ruff format check on touched tests: passed.
- `git diff --check`: passed.

## Downstream Compatibility

No production source, API route, OpenAPI contract, database schema, Kafka topic, event payload, or
runtime behavior changed. This slice repairs stale and order-dependent tests so CI evaluates the
current structured observability and read-model contracts reliably.

## Documentation And Wiki Decision

Updated this architecture record and the codebase review ledger. No README or wiki update is
required because this is a CI fix-forward test-contract slice without operator-facing behavior
change.
