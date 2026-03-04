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

The platform has implemented a meaningful portion of this architecture:
1. Shared config primitives (`portfolio_common.config`) are established and widely consumed.
2. Strong schema validation exists at API/DTO/event boundaries.
3. Some typed runtime settings already exist (for example in calculator engine modules).

However, full convergence is incomplete:
1. Ingestion hotspot modules are migrated to typed settings, but this pattern is not yet uniformly rolled out to all services.
2. Configuration guardrails exist for ingestion hotspot modules, but repository-wide enforcement is still pending.

RFC 002 therefore remains **Partially Implemented**.

## Original Requested Requirements (Preserved)
The original RFC requested:
1. Service configuration modeled with schema validation (typed settings).
2. Shared configuration library for cross-service defaults/utilities.
3. Unified startup loading with strict validation and fail-fast semantics.
4. Elimination of decentralized env parsing.
5. Operationally auditable, consistent configuration behavior.

## Original Proposal vs Implemented Reality
### Originally Proposed
1. Uniform typed settings pattern across services.
2. Centralized config package and startup validation flow.
3. Minimal ad-hoc environment parsing in service modules.

### Implemented Reality
1. Shared package exists and is in production use:
   - `src/libs/portfolio-common/portfolio_common/config.py`
2. Config-aware services/routers consume shared constants and helpers.
3. Typed settings are present in some domains:
   - `src/libs/financial-calculator-engine/src/core/config/settings.py`
4. Ingestion control modules now consume centralized typed settings:
   - `src/services/ingestion_service/app/ops_controls.py`
   - `src/services/ingestion_service/app/services/ingestion_job_service.py`
   - `src/services/ingestion_service/app/settings.py`

### Why the implemented approach is better than the historical wording
1. The system converged on `portfolio_common.config` rather than introducing a second config package name, reducing indirection.
2. Runtime policy complexity (capacity bands, replay controls, auth modes) matured materially and required practical staged migration instead of forced big-bang centralization.
3. Existing design preserves backward compatibility while enabling incremental hardening.

## Terminology and Naming Normalization
Legacy/outdated naming in earlier RFC language has been normalized:
1. `portfolio-config` -> `portfolio_common.config` (actual implementation package).
2. "all env loaded only at startup" -> "typed startup validation target; currently mixed with module-level env reads in selected services".
3. "centralized complete" -> "centralized base with partial service convergence".

## Requirement-to-Implementation Traceability
| Requirement | Current Implementation | Status | Evidence |
| --- | --- | --- | --- |
| Shared config library | Shared defaults/topics/runtime knobs centralized | Implemented | `src/libs/portfolio-common/portfolio_common/config.py` |
| Typed settings usage | Exists in select modules but not repo-wide | Partial | `src/libs/financial-calculator-engine/src/core/config/settings.py` |
| Fail-fast startup validation | Present in slices; not consistently enforced for all service config classes | Partial | service startup/runtime behavior patterns |
| Eliminate ad-hoc env access | Completed for ingestion hotspot modules via typed settings | Partial | `src/services/ingestion_service/app/settings.py`; `ops_controls.py`; `ingestion_job_service.py` |
| Consistent conventions and governance | Ingestion-focused guardrail implemented; repo-wide guardrail still pending | Partial | `scripts/config_access_guard.py`; `Makefile`; open delta `RFC-002-D02` |

## Configuration Layering Model (Target Standard)
The target model clarified by this RFC:
1. **Layer 1 (Platform shared)**:
   - Cross-service defaults, topic names, common guardrails in `portfolio_common.config`.
2. **Layer 2 (Service typed settings)**:
   - Service-local typed wrappers validate environment values and policy JSON structures.
3. **Layer 3 (Runtime usage)**:
   - Business logic reads typed settings objects, not raw environment values.
4. **Layer 4 (Governance/CI)**:
   - CI/lint guardrails prevent new direct `os.getenv` usage outside approved settings modules.

## Deterministic Configuration Resolution Algorithm
For each configurable runtime parameter `P`:
1. Resolve raw input from environment or default source.
2. Parse and type-coerce into strict typed schema.
3. Validate range/domain constraints (for example non-negative thresholds, enum values, JSON schema).
4. On invalid value:
   - fail fast at startup for critical controls, or
   - reject request-path override with deterministic error.
5. Expose effective values through operations/config endpoints for auditable runtime behavior.

This algorithm is partially implemented today and is the required standard for completion.

## Architectural Trade-offs
1. **Staged migration vs big-bang rewrite**:
   - Pros: avoids broad regressions and preserves endpoint behavior.
   - Cons: temporary mixed config patterns persist.
2. **Shared constants vs service autonomy**:
   - Pros: reduces duplication and drift.
   - Cons: requires clear boundaries to avoid overloading the shared module.
3. **Fail-fast strictness**:
   - Pros: higher operational reliability.
   - Cons: stricter startup can surface more deployment-time failures until config hygiene is complete.

## Gaps Still Open (Relevant and Pending)
1. `RFC-002-D01` (done):
   - Ingestion runtime env parsing consolidated into typed settings module.
2. `RFC-002-D02` (in progress):
   - Guardrail exists for ingestion hotspot modules; repository-wide config layering/guardrail still to be completed.

These are still relevant and should be implemented before RFC 002 can be marked `Implemented`.

## Test and Validation Evidence
Current evidence supporting partial completion:
1. Ingestion policy and guardrail contract tests:
   - `tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py`
2. Capacity operating-band and status tests:
   - `tests/unit/services/ingestion_service/services/test_ingestion_job_service_capacity_status.py`
3. Ingestion integration contract coverage:
   - `tests/integration/services/ingestion_service/test_ingestion_routers.py`
4. Shared config and runtime override handling:
   - `src/libs/portfolio-common/portfolio_common/config.py`
5. Typed ingestion settings and migration coverage:
   - `src/services/ingestion_service/app/settings.py`
   - `tests/unit/services/ingestion_service/test_settings.py`
6. Config access guardrail:
   - `scripts/config_access_guard.py`
   - `Makefile` (`config-access-guard`)

## Acceptance Criteria Alignment
1. Typed service configuration everywhere: **not yet aligned**.
2. Fully centralized and auditable config loading: **partially aligned**.
3. Elimination of ad-hoc env parsing: **not yet aligned**.
4. Clear cross-service configuration conventions: **partially aligned**.

## Proposed Completion Plan (Implementation-Oriented)
1. Implement typed settings wrappers for:
   - ingestion ops controls
   - ingestion job service policy and thresholds
2. Refactor runtime modules to consume those wrappers (remove direct raw env reads).
3. Add CI guard/check for unauthorized `os.getenv` usage outside approved settings modules.
4. Keep endpoint contracts stable while migrating internals.

## Backward Compatibility
Completion work is additive/refactoring in nature and should not require API contract changes if done correctly.

## Open Question
1. Should CI guardrails allow a temporary explicit allowlist for legacy modules during migration, or enforce immediate hard-fail once typed settings wrappers are introduced?

## Next Actions
1. Keep RFC 002 status as `Partially Implemented`.
2. Complete `RFC-002-D02` with repository-wide configuration layering and guardrail enforcement.
3. Reclassify RFC 002 to `Implemented` once the typed settings + guardrail pattern is broadly enforced across services.
