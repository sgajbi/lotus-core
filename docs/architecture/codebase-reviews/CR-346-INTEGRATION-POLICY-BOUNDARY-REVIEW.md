# CR-346 Integration Policy Boundary Review

Date: 2026-05-27

## Scope

Reviewed the policy-resolution block inside `IntegrationService`, the largest query-service service
module.

## Findings

`IntegrationService` mixed source-data product serving with integration snapshot policy concerns:
consumer-system normalization, environment-backed policy loading, tenant/global section matching,
strict-mode resolution, policy provenance, and effective-policy response construction. The logic was
self-contained and already had direct tests, making it a good candidate for modular extraction.

## Actions Taken

Extracted policy logic into `src/services/query_service/app/services/integration_policy.py`.

The integration service now owns the public `get_effective_policy(...)` service method and delegates
policy construction to the new module. The new policy module owns:

1. consumer-system canonicalization,
2. policy JSON loading and fallback behavior,
3. section normalization,
4. global and tenant policy matching,
5. policy context derivation,
6. effective policy response assembly.

Updated existing tests to target the policy module directly for policy helpers and context
resolution while preserving service-level `get_effective_policy(...)` coverage.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q
93 passed

python -m ruff check src/services/query_service/app/services/integration_service.py src/services/query_service/app/services/integration_policy.py tests/unit/services/query_service/services/test_integration_service.py
All checks passed
```

## Follow-Up

Continue decomposing `integration_service.py` by self-contained source-data product families rather
than moving unrelated methods in one large refactor. No API or wiki source change is required for
this slice because public contract behavior did not change.
