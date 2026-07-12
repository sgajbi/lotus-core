# CR-720 DPM Portfolio Universe Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_dpm_portfolio_universe_candidates(...)` in the DPM source-data product
support path.

## Finding

DPM portfolio-universe candidate resolution is a high-value source-data product for rebalance,
model-change, and advisor workflow integration, but response policy was still embedded in the
integration service. Read-scope normalization, page-token scope validation, continuation-token
payload policy, candidate DTO mapping, supportability, selection basis, lineage, and runtime
metadata all lived beside repository orchestration.

That made this large-page source-data path harder to audit and increased the risk of divergent
pagination or supportability semantics in future DPM readiness flows.

## Action

Added `dpm_portfolio_universe.py` as the focused DPM universe response and read-scope boundary.

The service now delegates scope normalization, scoped cursor validation, next-token payload policy,
and final response assembly while preserving the repository predicate shape and token encoding
boundary. Focused helper coverage locks normalized filters, wrong-scope page-token rejection,
cursor sort-key extraction, ready, partial-page, and empty-universe supportability,
selection-basis semantics, evidence timestamp selection, source-batch fingerprint, and snapshot
identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_dpm_portfolio_universe.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\dpm_portfolio_universe.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_dpm_portfolio_universe.py
python -m ruff format --check src\services\query_service\app\services\dpm_portfolio_universe.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_dpm_portfolio_universe.py
git diff --check
```
