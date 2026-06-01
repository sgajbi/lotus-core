# CR-729 External Hedge Execution Readiness Response Boundary

## Status

Hardened on 2026-06-01.

## Scope

`IntegrationService.get_external_hedge_execution_readiness(...)` in the external treasury
source-data product support path.

## Finding

External hedge execution readiness is intentionally fail-closed until bank-owned treasury source
ingestion is certified, but the unavailable response posture was assembled inline in the integration
service. Missing external treasury data families, blocked non-claim capabilities, lineage,
fingerprinting, snapshot identity, and runtime metadata lived beside mandate binding resolution.

That made the execution-readiness boundary harder to audit and increased the chance that future
downstream `lotus-manage` integration work would accidentally weaken the unavailable posture while
only changing service orchestration.

## Action

Added `external_hedge_execution_readiness.py` as the focused fail-closed response boundary.

The service now resolves the mandate binding and delegates unavailable response assembly. Focused
helper coverage locks the missing treasury source families, blocked non-claim capabilities, empty
readiness checks, lineage, data-quality status, sorted request fingerprinting, and deterministic
snapshot identity.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal query-service assembly
boundary and does not alter operator commands, migration policy, or published database runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_external_hedge_execution_readiness.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m alembic heads
python scripts\migration_contract_check.py --mode alembic-sql
python -m ruff check src\services\query_service\app\services\external_hedge_execution_readiness.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_external_hedge_execution_readiness.py
python -m ruff format --check src\services\query_service\app\services\external_hedge_execution_readiness.py src\services\query_service\app\services\integration_service.py tests\unit\services\query_service\services\test_external_hedge_execution_readiness.py
git diff --check
```
