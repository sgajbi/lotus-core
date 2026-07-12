# CR-1302 Position Valuation Reconciliation Policy

## Scope

Issue cluster: GitHub issue #658.

This slice extracts a representative financial reconciliation policy and value-object boundary for
position valuation checks.

## Objective

Move position valuation reconciliation arithmetic and finding classification out of the application
service into pure domain policy functions that do not import DTOs, ORM models, repositories,
database sessions, FastAPI, or Kafka.

## Changes

1. Added `financial_reconciliation_service.app.domain.reconciliation_policies` with:
   - `PositionValuationEvidence`;
   - `ReconciliationFinding`;
   - `ReconciliationSummary`;
   - `expected_market_value_local(...)`;
   - `requires_authoritative_fx_rate(...)`;
   - `position_valuation_reconciliation_findings(...)`.
2. Added `financial_reconciliation_service.app.adapters.reconciliation_finding_mapper` to map
   domain findings to `FinancialReconciliationFinding` ORM rows at the persistence boundary.
3. Rewired `ReconciliationService.run_position_valuation(...)` so it loads evidence through the
   repository, invokes the pure policy, maps domain findings through the adapter, persists rows, and
   stores a domain summary.
4. Left transaction cashflow and timeseries integrity finding construction in the service for
   future focused slices.

## Behavior And Compatibility

This is a design-modularity slice inside the existing financial reconciliation deployable. It is
not a runtime service split.

No route path, request DTO, response DTO, OpenAPI metadata, repository method signature, database
schema, stored status value, finding row field, finding value, summary field, metric name, metric
label value, dedupe key, correlation behavior, FX lookup behavior, or bond-pricing behavior
changed.

## Validation Evidence

Focused local validation before docs update:

1. `python -m pytest tests\unit\services\financial_reconciliation_service\domain\test_reconciliation_policies.py tests\unit\services\financial_reconciliation_service\adapters\test_reconciliation_finding_mapper.py tests\unit\services\financial_reconciliation_service\test_reconciliation_service.py tests\unit\services\financial_reconciliation_service\domain\test_reconciliation_run_lifecycle_policy.py -q`
   - 25 passed.
2. Scoped Ruff lint passed.
3. Scoped Ruff format required mechanical formatting of `reconciliation_service.py`; final format
   evidence is recorded before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger and repo-local engineering context.

No wiki update is required because no operator command, API route behavior, runtime support
workflow, user-facing capability, or published wiki truth changed.

No central Lotus skill change is required. The repeatable pattern is repo-local: financial
reconciliation rules should move behind pure domain policies with domain findings and persistence
adapters before service orchestration changes.

## Remaining Work

GitHub issue #658 is locally fixed for the representative-policy acceptance criteria pending PR
CI/QA and issue closure. Future slices should migrate transaction cashflow, timeseries integrity,
and authoritative timeseries aggregation rules behind the same policy/value-object boundary.
