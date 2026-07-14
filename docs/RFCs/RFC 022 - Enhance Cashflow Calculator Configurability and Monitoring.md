# RFC 022 - Enhance Cashflow Calculator Configurability and Monitoring

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-09-02 |
| Last Updated | 2026-07-14 |
| Owners | `portfolio_transaction_processing_service` |
| Depends On | RFC 001 |
| Scope | DB-driven cashflow rules, runtime rule refresh behavior, business-level cashflow metrics |

## Executive Summary

RFC 022 modernized cashflow processing by moving rule logic from static code config to database policy records and adding business-level metrics.

Current implementation is complete:
1. DB-driven `cashflow_rules` and repository loading are implemented.
2. `cashflows_created_total` metric is implemented and emitted with `classification`/`timing` labels.
3. Runtime no-restart rule update behavior is implemented with TTL refresh, explicit invalidation hook, and missing-rule forced refresh safeguard.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 022 requested:
1. Create `cashflow_rules` table and remove hardcoded mapping.
2. Load rules via repository and in-memory cache for runtime processing.
3. Add `cashflows_created_total` metric by classification/timing.
4. Support dynamic rule updates without requiring service restarts.

## Current Implementation Reality

Implemented:
1. `cashflow_rules` schema exists via Alembic migration.
2. Service loads rules from DB through `CashflowRulesRepository`.
3. Combined transaction processing uses an instance-owned in-memory cache with deterministic
   refresh controls:
   1. TTL-based refresh (`CASHFLOW_RULE_CACHE_TTL_SECONDS`).
   2. Explicit runtime-owned invalidation (`CashflowRuleCache.invalidate`).
   3. Missing-rule forced refresh to pick up newly added rule types immediately.
4. Missing rule path sends event to DLQ as non-retryable configuration error.
5. `CASHFLOWS_CREATED_TOTAL` counter is defined and incremented in `CashflowLogic.calculate`.
6. Unit tests cover repository behavior, consumer behavior, and cache refresh semantics.

Evidence:
- `alembic/versions/1a7b8c9d0e2f_feat_add_cashflow_rules_table.py`
- `src/services/portfolio_transaction_processing_service/app/infrastructure/cashflow/rule_repository.py`
- `src/services/portfolio_transaction_processing_service/app/infrastructure/cashflow/rule_cache.py`
- `src/services/portfolio_transaction_processing_service/app/infrastructure/cashflow_staging_workflow.py`
- `src/services/portfolio_transaction_processing_service/app/domain/cashflow/calculation.py`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`
- `tests/unit/services/portfolio_transaction_processing_service/infrastructure/cashflow/test_rule_repository.py`
- `tests/unit/services/portfolio_transaction_processing_service/infrastructure/cashflow/test_rule_cache.py`
- `tests/unit/services/portfolio_transaction_processing_service/cashflow/test_cashflow_staging_workflow.py`
- `tests/unit/services/portfolio_transaction_processing_service/cashflow/test_cashflow_calculation.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Replace hardcoded rules with DB policy table | Implemented (`cashflow_rules`) | migration + repository |
| Load/cached rule lookup in combined processing | Implemented (instance-owned TTL cache + explicit invalidation + missing-rule forced refresh) | `cashflow/rule_cache.py`; mirrored infrastructure tests |
| Metric `cashflows_created_total` with labels | Implemented | `monitoring.py`; domain calculation adapter tests |
| Dynamic rule updates without restart | Implemented | source-versioned rule cache; `test_rule_cache.py` |

## Design Reasoning and Trade-offs

1. DB-driven rules improve governance and remove business-policy code redeploy dependency.
2. In-memory caching preserves consumer throughput.
3. TTL + forced refresh keeps runtime agility without requiring restarts.

Trade-off:
- Very low-frequency rule changes may still wait up to TTL unless missing-rule path or explicit invalidation is used.

## Gap Assessment

No blocking implementation gap remains for RFC-022 scope.

## Proposed Changes

1. Keep cache-policy controls (`CASHFLOW_RULE_CACHE_TTL_SECONDS`, invalidation hook) documented and regression-tested.

## Test and Validation Evidence

1. Repository query behavior tests:
   - `tests/unit/services/portfolio_transaction_processing_service/infrastructure/cashflow/test_rule_repository.py`
2. Runtime cache/rule usage tests:
   - `tests/unit/services/portfolio_transaction_processing_service/infrastructure/cashflow/test_rule_cache.py`
3. Metric emission tests:
   - `tests/unit/services/portfolio_transaction_processing_service/cashflow/test_cashflow_calculation.py`

## Original Acceptance Criteria Alignment

Aligned:
1. Schema and DB-driven configuration: met.
2. Business metric instrumentation: met.
3. Runtime no-restart dynamic update behavior: met.

## Rollout and Backward Compatibility

1. Runtime behavior remains backward-compatible.
2. Rule-update responsiveness is improved without requiring process restart.

## Next Actions

1. Maintain cache refresh regression tests at the mirrored infrastructure boundary.
