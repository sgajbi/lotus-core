# RFC 002 - Centralized Configuration Management

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | Historical RFC baseline (date not recorded in file) |
| Last Updated | 2026-03-04 |
| Owners | lotus-core platform and service maintainers |
| Depends On | RFC 001 (operational baseline context) |
| Related Standards | `docs/standards/enterprise-readiness.md`, `docs/standards/durability-consistency.md` |
| Scope | In repo (`lotus-core`) |

## Executive Summary

RFC 002 defines a centralized, validated configuration model across lotus-core services.
The objective is fail-fast startup safety, consistency, and maintainability as service count grows.

Current state is partially implemented: common config primitives and typed settings exist, but full repository-wide convergence is not complete.

## Original Requested Requirements (Preserved)

The original RFC requested:
1. Service configuration modeled with schema validation (Pydantic-style typed settings).
2. Shared configuration library for cross-service defaults/utilities.
3. Unified loading at startup with strict validation and fail-fast behavior.
4. Reduced decentralized env parsing to improve consistency and maintainability.
5. Operationally clearer and more auditable config behavior across services.

## Current Implementation Reality

Centralization is present, but not uniform.

Implemented parts:
1. Shared configuration module exists in `portfolio_common.config`.
2. Multiple services consume shared config constants (Kafka topics, calendar defaults, runtime overrides).
3. DTO-level validation is strong across ingestion/query contracts (Pydantic models).
4. Some domains already use typed settings (`financial-calculator-engine` with `BaseSettings`).

Evidence:
- `src/libs/portfolio-common/portfolio_common/config.py`
- `src/libs/financial-calculator-engine/src/core/config/settings.py`
- `src/services/ingestion_service/app/DTOs/*.py`
- `src/services/query_service/app/repositories/*` (imports from shared config)

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation | Status | Evidence |
| --- | --- | --- | --- |
| Shared config library | `portfolio_common.config` provides shared defaults/topics/guards | Implemented | `portfolio_common/config.py` |
| Typed settings usage | Present in calculator engine and parts of services | Partial | `financial-calculator-engine/src/core/config/settings.py` |
| Fail-fast startup validation | Present in selected service paths; not fully uniform repo-wide | Partial | service startup/runtime checks |
| Eliminate ad-hoc env access | Not fully achieved; direct env reads remain in key modules | Gap | `ingestion_service/app/ops_controls.py`; `ingestion_job_service.py` |
| Consistent config conventions | Improved but still mixed patterns across services | Partial | cross-service config usage patterns |

## Design Reasoning and Trade-offs

1. **Centralized contract first**: shared config primitives reduce drift for cross-service values (topics, common thresholds, policies).
2. **Service-local typed wrappers**: necessary for service-specific policy semantics without polluting common library.
3. **Fail-fast over runtime surprises**: startup validation is preferred for high-signal operational reliability.
4. **Trade-off**: migration from ad-hoc env access to typed settings requires staged rollout to avoid contract regressions.

## Gap Assessment

The RFC target is not fully achieved yet.

1. Runtime config is still partly decentralized:
   - `src/services/ingestion_service/app/ops_controls.py` reads env directly.
   - `src/services/ingestion_service/app/services/ingestion_job_service.py` contains many service-local env reads and policy parsing.
2. No single repo-wide typed settings contract is enforced for all services.
3. The original RFC language references a new library name (`portfolio-config`) that does not match current implementation (`portfolio_common.config`).

## Deviations and Evolution Since Original RFC

1. Implementation standardized on `portfolio_common.config` rather than creating a separate `portfolio-config` package.
2. Runtime policy-heavy ingestion modules evolved faster than config convergence, leaving concentrated env parsing hotspots.
3. Later operational RFCs expanded policy/config complexity (capacity bands, replay controls), increasing need for typed consolidation.

## Proposed Changes

1. Keep `portfolio_common.config` as canonical shared runtime config package (no need to introduce a second library name).
2. Introduce typed settings wrappers for ingestion ops/policy config to replace scattered `os.getenv` blocks.
3. Standardize startup validation behavior and fail-fast semantics across services with typed settings.
4. Document configuration ownership boundaries:
   - shared platform-level defaults in `portfolio_common.config`
   - service-specific typed settings modules consuming shared defaults

## Test and Validation Evidence

Current evidence of config-contract quality:
1. Ingestion policy/guardrail config endpoints and contract tests:
   - `tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py`
   - `tests/integration/services/ingestion_service/test_ingestion_routers.py`
2. Capacity policy math and contract tests:
   - `tests/unit/services/ingestion_service/services/test_ingestion_job_service_capacity_status.py`
3. Shared config runtime override sanitization in common library:
   - `src/libs/portfolio-common/portfolio_common/config.py`

## Original Acceptance Criteria Alignment

Alignment status against original intent:
1. Services loading config via typed models: **partial**.
2. Fail-fast invalid configuration behavior: **partial**.
3. Consistent and manageable cross-service configuration: **partial**.
4. Documentation alignment to current pattern: **partially complete**, further governance clarity still needed.

## Rollout and Backward Compatibility

Changes should be non-breaking if done in phases:
1. Introduce typed settings in parallel with current env access.
2. Migrate service modules incrementally.
3. Remove legacy direct env access only after tests and endpoint contracts remain green.

## Open Questions

1. Should we enforce a lint/check rule that blocks new service code from direct `os.getenv` access outside approved settings modules?

## Next Actions

1. Classify RFC 002 as `Partially implemented (requires enhancement)`.
2. Create a migration slice to consolidate ingestion service env parsing into typed settings modules.
3. Define a repository-level configuration pattern standard and CI check to prevent config drift.
