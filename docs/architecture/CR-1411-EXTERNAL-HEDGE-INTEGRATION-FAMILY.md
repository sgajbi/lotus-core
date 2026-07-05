# CR-1411 External Hedge Integration Family

## Status

In progress on 2026-07-06.

## Scope

`IntegrationService` external hedge, treasury, and OMS source-data products in `query_service`.

## Finding

GitHub issue #548 remains valid: `IntegrationService` still carried multiple cohesive source-data
contract families as direct facade methods. The external hedge path was already fail-closed and
source-data product assembly lived in focused resolver modules, but the facade still owned direct
repository wiring for external hedge execution readiness, currency exposure, OMS order
acknowledgement, hedge policy, eligible hedge instruments, and FX forward curves.

That kept treasury/OMS product delegation coupled to the whole integration facade and made future
external hedge behavior harder to test without constructing unrelated integration dependencies.

## Action

Added `ExternalHedgeIntegrationService` as the external hedge contract-family boundary. The family
service owns the reference-repository provider and delegates to the existing external hedge,
treasury, and OMS resolver modules.

`IntegrationService` now constructs the family service from its existing dependency bundle and keeps
the public facade methods as thin compatibility delegates.

## Compatibility

No downstream API contract changes are intended in this slice. Existing route handlers and service
callers continue to use the same facade methods and DTO contracts. Fail-closed external treasury and
OMS supportability, lineage, data-quality status, snapshot identities, source-data product names,
and request semantics are unchanged.

## Remaining Issue Scope

This is a partial issue #548 slice. Additional contract-family extractions are still needed before
the issue should be marked fixed-local, including benchmark/reference products, tax/performance
economics products, client profile/income products, and remaining market/reference families.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_integration_service.py -q
python -m ruff check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\external_hedge_integration_service.py tests\unit\services\query_service\services\test_integration_service.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\external_hedge_integration_service.py tests\unit\services\query_service\services\test_integration_service.py
python -m mypy src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\external_hedge_integration_service.py
git diff --check
```
