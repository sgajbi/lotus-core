# RFC 022 - Enhance Cashflow Calculator Configurability and Monitoring

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-09-02 |
| Last Updated | 2026-03-05 |
| Owners | `cashflow_calculator_service`, `portfolio-common` |
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
3. Consumer uses in-memory cache with deterministic refresh controls:
   1. TTL-based refresh (`CASHFLOW_RULE_CACHE_TTL_SECONDS`).
   2. Explicit invalidation hook (`invalidate_cashflow_rule_cache`).
   3. Missing-rule forced refresh to pick up newly added rule types immediately.
4. Missing rule path sends event to DLQ as non-retryable configuration error.
5. `CASHFLOWS_CREATED_TOTAL` counter is defined and incremented in `CashflowLogic.calculate`.
6. Unit tests cover repository behavior, consumer behavior, and cache refresh semantics.

Evidence:
- `alembic/versions/1a7b8c9d0e2f_feat_add_cashflow_rules_table.py`
- `src/services/calculators/cashflow_calculator_service/app/repositories/cashflow_rules_repository.py`
- `src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py`
- `src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`
- `tests/unit/services/calculators/cashflow_calculator_service/unit/repositories/test_cashflow_rules_repository.py`
- `tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
- `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Replace hardcoded rules with DB policy table | Implemented (`cashflow_rules`) | migration + repository |
| Load/cached rule lookup in consumer | Implemented (TTL cache + explicit invalidation + missing-rule forced refresh) | `transaction_consumer.py`; consumer unit tests |
| Metric `cashflows_created_total` with labels | Implemented | `monitoring.py`; `cashflow_logic.py`; core tests |
| Dynamic rule updates without restart | Implemented | `transaction_consumer.py`; `test_cashflow_transaction_consumer.py` |

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
   - `tests/unit/services/calculators/cashflow_calculator_service/unit/repositories/test_cashflow_rules_repository.py`
2. Consumer cache/rule usage tests:
   - `tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
3. Metric emission tests:
   - `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`

## Original Acceptance Criteria Alignment

Aligned:
1. Schema and DB-driven configuration: met.
2. Business metric instrumentation: met.
3. Runtime no-restart dynamic update behavior: met.

## Rollout and Backward Compatibility

1. Runtime behavior remains backward-compatible.
2. Rule-update responsiveness is improved without requiring process restart.

## Next Actions

1. Maintain cache refresh regression tests as part of consumer suite.
