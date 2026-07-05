# CR-1382 Financial Reconciliation Enterprise Authorization

## Objective

Fix GitHub issue #498 by making financial reconciliation control endpoints use a service-local
enterprise-readiness boundary with exact capability rules for control-run creation and evidence
reads.

## Expected Improvement

- `financial_reconciliation_service` now owns default capability rules for every canonical
  `/reconciliation/*` business route instead of relying on generic shared defaults or environment
  JSON.
- Production-like or explicitly enforced environments require signed enterprise auth-context
  headers plus route-specific capabilities for reconciliation writes and reads.
- Route-coverage tests fail if a future reconciliation control endpoint is added without an
  explicit capability rule.
- Denied writes emit source-safe enterprise audit evidence through the existing shared middleware.

## Changes

- Added `src/services/financial_reconciliation_service/app/enterprise_readiness.py`.
- Wired `src/services/financial_reconciliation_service/app/main.py` through the service-local
  enterprise wrapper.
- Added unit tests for capability-rule route coverage, write/read denial, exact route matching,
  strict runtime configuration, and denied-write audit evidence.
- Added app integration tests for denied missing headers, denied missing write/read capability, and
  unauthenticated operational allowlist behavior.

## Compatibility

Local and test compatibility is preserved because enterprise auth enforcement remains opt-in
outside production-like profiles. Existing route paths, request DTOs, response DTOs, OpenAPI
metadata, database schema, reconciliation findings, summaries, metrics, and runtime topology are
unchanged.

Intentional production-security behavior: when write or read authorization is enabled, financial
reconciliation business routes require signed enterprise auth context and one of:

- `financial_reconciliation.controls.run`
- `financial_reconciliation.controls.read`

## Validation

Focused validation for this slice:

- `python -m pytest tests/unit/services/financial_reconciliation_service/test_enterprise_readiness.py tests/integration/services/financial_reconciliation_service/test_financial_reconciliation_app.py -q`
  - Result: 21 passed.
- `python -m pytest tests/unit/scripts/test_security_control_coverage_guard.py tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py -q`
  - Result: 38 passed.
- scoped Ruff lint and format checks for touched financial reconciliation source/test files.

## Documentation And Wiki Decision

Updated this architecture note, the codebase review ledger, and repo-local engineering context. No
README or wiki source update is needed because no operator command, public route, or published API
shape changed.

No platform skill update is required. The repeatable lesson is repo-local and now pinned by
financial reconciliation route-coverage tests plus repository context: enterprise middleware
installation is not sufficient without exact service-owned capability rules for business routes.

## Follow-Up

Issue #498 is locally fixed pending final gates, PR CI/QA, merge to `main`, and post-merge closure.
