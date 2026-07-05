# CR-1389 Risk-Based Test Coverage Matrix

## Objective

Fix GitHub issue #602 by adding a repository-owned matrix that maps critical `lotus-core`
domains to required proof families, existing evidence, known gaps, and follow-up issues.

## Changes

1. Added `docs/standards/risk-based-test-coverage-matrix.v1.json`.
2. Added `scripts/risk_based_test_coverage_matrix_guard.py`.
3. Added focused pass/fail tests for the guard.
4. Added pytest markers for API, contract/schema, middleware, security, regression/golden, and E2E
   proof families while keeping strict marker collection enabled.
5. Wired `make risk-based-test-coverage-matrix-guard` into `make lint`.

## Design-Time And Runtime Impact

This is a design-time governance and CI slice. It does not change runtime behavior, deployment
topology, database schema, event payloads, API response contracts, or downstream behavior.

The improvement is measurable because future high-risk changes now have a deterministic matrix
contract instead of implicit test-family expectations.

## Same-Pattern Scan

The existing `critical-path-coverage.v1.json` covers source coverage thresholds, but it does not
declare every critical business domain and proof family required by #602. The new matrix links to
existing Make targets and follow-up issues rather than duplicating the responsibilities of event,
security, integration, E2E, and coverage gates.

## Validation

Run before commit:

```powershell
python -m pytest tests/unit/scripts/test_risk_based_test_coverage_matrix_guard.py -q
python scripts/risk_based_test_coverage_matrix_guard.py
python -m ruff check scripts/risk_based_test_coverage_matrix_guard.py tests/unit/scripts/test_risk_based_test_coverage_matrix_guard.py --ignore E501,I001
python -m ruff format --check scripts/risk_based_test_coverage_matrix_guard.py tests/unit/scripts/test_risk_based_test_coverage_matrix_guard.py
make risk-based-test-coverage-matrix-guard
make quality-wiki-docs-gate
```

## Documentation And Context Decision

Repository context and testing strategy are updated because the repo-native test-governance contract
changed. No wiki source update is required: this is an engineer/agent CI contract, and the README/wiki
front door can continue linking to standards and testing strategy without adding a separate operator
page.
