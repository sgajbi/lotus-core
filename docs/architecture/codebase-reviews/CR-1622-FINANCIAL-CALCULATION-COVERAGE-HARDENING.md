# CR-1622: Financial Calculation Coverage Hardening

## Objective

Close the PR #784 financial critical-path coverage gap with domain-relevant tests while preserving the governed thresholds and transaction-processing behavior.

## Finding

The first complete PR coverage run passed 4,645 unit tests and 136 integration-lite tests, but the changed financial-calculation group measured 91.49% line coverage against a 92% minimum and 83.93% branch coverage against an 85% minimum. The uncovered paths included cross-currency booking without an FX rate, invalid adjustment direction, and unexpected cost-transaction model construction failure.

## Change

- Added a cross-currency BUY scenario proving that missing FX evidence fails closed before cost or lot mutation.
- Added an adjustment scenario proving that a non-domain movement direction is rejected before financial state mutation.
- Added parser recovery coverage proving that an unexpected transaction-model construction failure becomes a deterministic diagnostic stub and collected error.

## Complexity Decision

The slice extends the existing domain-owned test modules and reuses the governed coverage gate. It adds no production branch, compatibility path, fixture framework, helper abstraction, threshold exception, or parallel coverage command.

## Measurable Improvement

- Financial critical-path line coverage increased from 91.49% to 92.91%.
- Financial critical-path branch coverage increased from 83.93% to 85.12%.
- `transaction_parser.py` increased from 81.48% line coverage to 100%, while retaining 100% branch coverage.
- `cost_basis_calculator.py` increased from 88.54% to 89.58% line coverage and from 81.43% to 82.86% branch coverage.

## Validation

- Focused cost calculator and parser suite: 82 passed.
- Scoped Ruff lint and format checks: passed.
- `make coverage-gate`: 4,648 unit tests passed, 10 deselected, zero warnings; 136 integration-lite tests passed; aggregate Query Service coverage met the displayed 98% requirement; every critical-path threshold passed.

## Compatibility And Documentation Decision

Production code, API/event contracts, persistence, database structures, runtime topology, and downstream behavior are unchanged. The codebase-review ledger changes to preserve validation truth; README, wiki, API inventory, quality thresholds, repository context, and operator documentation require no change.

## Follow-Up

Push the signed fix-forward commit to PR #784, rerun required CI, and retain issue #779 in `status/pr-open` until the PR is merged and the exact `main` SHA is validated.
