# RFC 038 - Lotus Core Integration Capabilities API

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | `query-service` integration contracts |
| Depends On | ADR 003, RFC 035 integration patterns, RFC 042 policy overrides |
| Scope | Backend capability negotiation API for downstream consumers |

## Executive Summary

RFC 038 is implemented in query-service:
1. `GET /integration/capabilities` exists with consumer + tenant context.
2. Response includes contract metadata, input-mode support, feature flags, and workflow flags.
3. Tenant-aware policy overrides and policy-version provenance are supported.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 038 requested:
1. Single discoverable capabilities endpoint for lotus-core integration behavior.
2. Inputs: `consumer_system` and `tenant_id`.
3. Outputs: contract metadata, supported input modes, feature/workflow capability flags.
4. Backend-owned policy resolution, initially environment-backed with future centralization path.

## Current Implementation Reality

Implemented:
1. Capabilities router endpoint with typed `ConsumerSystem` and tenant query parameters.
2. Service-level policy resolution with:
   - default feature states,
   - workflow dependency derivation,
   - tenant override JSON support,
   - policy version resolution.
3. Input mode shaping based on feature states (for example disabling `inline_bundle` or `file_upload` when adapter capabilities are off).
4. Capability response includes `contract_version`, `source_service`, `as_of_date`, `generated_at`, `policy_version`, feature/workflow entries.
5. Unit and integration tests validate happy paths and override behavior.

Evidence:
- `src/services/query_service/app/routers/capabilities.py`
- `src/services/query_service/app/services/capabilities_service.py`
- `src/services/query_service/app/dtos/capabilities_dto.py`
- `tests/unit/services/query_service/services/test_capabilities_service.py`
- `tests/integration/services/query_service/test_capabilities_router_dependency.py`
- `docs/architecture/adr_003_integration_capabilities_api.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Single capabilities endpoint | Implemented | capabilities router |
| Consumer + tenant context input | Implemented | query parameters and DTO typing |
| Feature/workflow capability metadata output | Implemented | capabilities DTO/service |
| Backend-owned policy resolution | Implemented with env + tenant override model | capabilities service |
| Centralization-ready evolution path | Explicitly documented in ADR/RFC; still environment-backed runtime | ADR 003 + service design |

## Design Reasoning and Trade-offs

1. Moving capability logic into backend removes UI/gateway hardcoded behavior matrices.
2. Workflow derivation from feature dependencies provides deterministic behavior and easier contract testing.
3. Tenant override support enables controlled rollout differences without forked APIs.

Trade-off:
- Environment and JSON override governance can become hard to manage at scale until policy-pack/control-plane centralization is adopted.

## Gap Assessment

No blocking implementation gap for RFC 038 accepted scope.
Centralized policy control-plane migration is valid future architecture work but was not a baseline acceptance blocker.

## Deviations and Evolution Since Original RFC

1. Implementation includes richer metadata (`as_of_date`, `policy_version`) than minimal initial framing.
2. Tenant override behavior is already implemented rather than left purely conceptual.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.
2. Continue control-plane centralization as a future enhancement stream, not an RFC 038 incompleteness defect.

## Test and Validation Evidence

1. Capabilities service unit tests:
   - `tests/unit/services/query_service/services/test_capabilities_service.py`
2. Router dependency integration tests:
   - `tests/integration/services/query_service/test_capabilities_router_dependency.py`

## Original Acceptance Criteria Alignment

Aligned:
1. Endpoint contract exists and is test-covered.
2. Backend-driven capability policy model is operational.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. When centralized policy service is introduced, should `policy_version` semantics remain service-local or become globally versioned across Lotus apps?

## Next Actions

1. Keep compatibility tests stable as feature/workflow catalog evolves.
