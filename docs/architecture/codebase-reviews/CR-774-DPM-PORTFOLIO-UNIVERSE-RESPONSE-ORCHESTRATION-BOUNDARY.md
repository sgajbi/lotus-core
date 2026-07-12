# CR-774 DPM Portfolio Universe Response Orchestration Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.resolve_dpm_portfolio_universe_candidates(...)` in the DPM portfolio-universe
source-data path.

## Finding

DPM portfolio-universe orchestration still coordinated read-scope normalization, page-token decoding,
cursor validation, repository page reads, page slicing, continuation-token encoding, and response
assembly inline in the broad integration service.

That left the integration service as the owner of DPM universe paging workflow policy even though
the DPM portfolio-universe module already owned scope normalization, cursor policy, token payload
shape, supportability, selection basis, lineage, and runtime metadata.

## Action

Added `dpm_portfolio_universe_page_token(...)` and
`resolve_dpm_portfolio_universe_candidate_response(...)` to `dpm_portfolio_universe.py`, then routed
`IntegrationService.resolve_dpm_portfolio_universe_candidates(...)` through that helper with the
existing reference repository and page-token codec dependencies.

The service still owns dependency wiring. The DPM portfolio-universe module now owns the full
source-data response workflow after dependency injection: read-scope normalization, page-token
scope validation, repository paging arguments, page slicing, next-page token creation, and response
assembly. Focused helper coverage locks repository read arguments, normalized filters, encoded
token payload shape, terminal-page token suppression, and returned page shape.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service
modularization boundary and does not alter API shape, operator commands, migration policy, or
published database runbooks.

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
