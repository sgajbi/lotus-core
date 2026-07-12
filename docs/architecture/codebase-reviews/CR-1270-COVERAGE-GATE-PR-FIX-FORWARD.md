# CR-1270 Coverage Gate PR Fix-Forward

Date: 2026-07-01

## Objective

Fix the PR #695 `PR Merge Gate / Coverage Gate (Combined)` failure by adding meaningful
query-service contract coverage instead of lowering the branch-aware 98% coverage threshold.

## Change

- Added DTO contract tests for market-data coverage, DPM source readiness, instrument eligibility,
  portfolio tax-lot, performance component economics, and reporting request validation branches.
- Added page-token codec tests for malformed envelopes, non-string signatures, non-dict payloads,
  and invalid signatures.
- Added performance component economics tests for trade-fee fallback, non-positive fee omission,
  anonymous cost component grouping, and empty evidence supportability.

## Validation Evidence

- Focused DTO/page-token/performance economics tests: 65 passed.
- `make coverage-gate`: unit suite 3438 passed, integration-lite suite 126 passed, combined
  branch-aware coverage total 98%.

## Downstream Compatibility

No production source, API route, OpenAPI contract, database schema, Kafka topic, event payload, or
runtime behavior changed. This slice strengthens tests for existing public request-validation,
pagination-security, and component-economics behavior.

## Documentation And Wiki Decision

Updated this architecture record and the codebase review ledger. No README or wiki update is
required because this is a CI fix-forward test-coverage slice without operator-facing behavior
change.
