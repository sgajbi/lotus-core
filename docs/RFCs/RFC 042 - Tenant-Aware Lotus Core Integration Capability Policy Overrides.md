# RFC 042 - Tenant-Aware Lotus Core Integration Capability Policy Overrides

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | `query-service` |
| Depends On | RFC 038 |
| Scope | Tenant-level overrides for `/integration/capabilities` policy resolution |

## Executive Summary

RFC 042 is implemented.
Capabilities resolution now supports tenant-aware overrides with deterministic fallback behavior:
1. Global feature defaults resolve first.
2. Tenant overrides apply next when present and valid.
3. Consumer/default input mode overrides are resolved from tenant policy.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 042 requested:
1. Tenant-aware policy overrides for integration capabilities.
2. Stable API contract shape while allowing backend-controlled rollout variance.
3. Validation/fallback behavior for malformed policy inputs.

## Current Implementation Reality

Implemented:
1. `LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON` is parsed by capabilities service with robust invalid-input fallback.
2. Supported override dimensions are applied:
   - `policy_version`,
   - feature flags,
   - workflow flags,
   - consumer/default supported input modes.
3. Integration capabilities response reflects resolved tenant context and policy metadata.
4. Unit and integration tests cover default, overridden, and invalid override scenarios.

Evidence:
- `src/services/query_service/app/services/capabilities_service.py`
- `src/services/query_service/app/routers/capabilities.py`
- `src/services/query_service/app/dtos/capabilities_dto.py`
- `tests/unit/services/query_service/services/test_capabilities_service.py`
- `tests/integration/services/query_service/test_capabilities_router_dependency.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Tenant-aware capability policy | Implemented | capabilities service override loader/resolution |
| Stable contract shape | Implemented | capabilities DTO and router |
| Safe fallback for malformed overrides | Implemented | invalid JSON/object handling + unit tests |

## Design Reasoning and Trade-offs

1. Backend-owned tenant policy keeps UI/gateway behavior contract-driven and avoids client-side feature logic sprawl.
2. Override model enables controlled rollout and per-tenant operating mode differences without code deployments.

Trade-off:
- Environment JSON policy management can become difficult to govern at scale without centralized policy infrastructure.

## Gap Assessment

No high-value implementation gap for RFC 042 scope.

## Deviations and Evolution Since Original RFC

1. Runtime implementation includes richer workflow derivation and input-mode filtering behavior tied to feature dependencies.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.
2. Treat centralized policy service migration as future architecture enhancement.

## Test and Validation Evidence

1. `tests/unit/services/query_service/services/test_capabilities_service.py`
2. `tests/integration/services/query_service/test_capabilities_router_dependency.py`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None for baseline RFC 042 scope.

## Next Actions

1. Keep tenant override behaviors covered as feature catalog grows.

