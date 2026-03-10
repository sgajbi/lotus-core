# RFC 002 - Centralized Configuration Management

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | Historical RFC baseline (date not recorded in file) |
| Last Updated | 2026-03-05 |
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

Convergence is now complete for service-level configuration layering:
1. Ingestion, query-service, and valuation-service hotspot modules are migrated to typed settings.
2. Repository-wide configuration guardrail enforcement blocks new direct env access outside approved settings/config modules.

RFC 002 is now **Implemented**.

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
   - `src/services/calculators/cost_calculator_service/app/cost_engine/src/core/config/settings.py`
4. Ingestion control modules now consume centralized typed settings:
   - `src/services/ingestion_service/app/ops_controls.py`
   - `src/services/ingestion_service/app/services/ingestion_job_service.py`
   - `src/services/ingestion_service/app/settings.py`
5. Query-service control modules now consume centralized typed settings:
   - `src/services/query_service/app/settings.py`
   - `src/services/query_service/app/services/capabilities_service.py`
   - `src/services/query_service/app/services/integration_service.py`
   - `src/services/query_service/app/services/analytics_timeseries_service.py`
   - `src/services/query_service/app/enterprise_readiness.py`

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
| Typed settings usage | Implemented for active service hotspots and policy surfaces | Implemented | `src/services/ingestion_service/app/settings.py`; `src/services/query_service/app/settings.py`; `src/services/calculators/position_valuation_calculator/app/settings.py` |
| Fail-fast startup validation | Implemented through typed parsing/guarded defaults in service settings modules | Implemented | settings modules + unit tests |
| Eliminate ad-hoc env access | Implemented for service modules in scope, with direct env reads confined to approved settings/config modules | Implemented | `scripts/config_access_guard.py`; `src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py`; `src/services/calculators/position_valuation_calculator/app/core/reprocessing_worker.py` |
| Consistent conventions and governance | Repo-wide guardrail enforced in CI/local lint path | Implemented | `scripts/config_access_guard.py`; `Makefile` |

## Configuration Layering Model (Target Standard)
The target model clarified by this RFC:
1. **Layer 1 (Platform shared)**:
   - Cross-service defaults, topic names, common guardrails in `portfolio_common.config`.
2. **Layer 2 (Service typed settings)**:
   - Service-local typed wrappers validate environment values and policy JSON structures.
3. **Layer 3 (Runtime usage)**:
   - Business logic reads typed settings objects, not raw environment values.
4. **Layer 4 (Governance/CI)**:
   - CI/lint guardrails prevent new direct `os.getenv` usage outside approved settings/config modules.

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
2. `RFC-002-D02` (done):
   - Repository-wide config guardrail now enforces no new direct env parsing outside approved modules.
3. `RFC-002-D04` (done):
   - Remaining valuation-service direct env reads were migrated to typed settings.

No open implementation deltas remain for RFC 002.

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
7. Query-service typed settings migration:
   - `src/services/query_service/app/settings.py`
   - `tests/unit/services/query_service/test_enterprise_readiness.py`
   - `tests/unit/services/query_service/services/test_capabilities_service.py`
   - `tests/unit/services/query_service/services/test_integration_service.py`
   - `tests/unit/services/query_service/services/test_analytics_timeseries_service.py`
8. Valuation-service typed settings migration:
   - `src/services/calculators/position_valuation_calculator/app/settings.py`
   - `src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py`
   - `src/services/calculators/position_valuation_calculator/app/core/reprocessing_worker.py`
   - `tests/unit/services/calculators/position_valuation_calculator/core/test_settings.py`
   - `tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py`
   - `tests/unit/services/calculators/position_valuation_calculator/core/test_reprocessing_worker.py`

## Acceptance Criteria Alignment
1. Typed service configuration everywhere in scoped active services: **aligned**.
2. Fully centralized and auditable config loading pattern: **aligned**.
3. Elimination of ad-hoc env parsing in service business modules: **aligned**.
4. Clear cross-service configuration conventions with CI guard: **aligned**.

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
1. Keep RFC 002 status as `Implemented`.
2. Continue enforcing `config-access-guard` to prevent regression.
3. Evaluate migration of shared-library env parsing (`portfolio_common/config.py`, `db.py`, `logging_utils.py`) only if future architectural standards require stricter centralization.
