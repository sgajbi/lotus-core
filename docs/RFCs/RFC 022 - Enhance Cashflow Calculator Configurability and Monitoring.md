# RFC 022 - Enhance Cashflow Calculator Configurability and Monitoring

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2025-09-02 |
| Last Updated | 2026-03-04 |
| Owners | `cashflow_calculator_service`, `portfolio-common` |
| Depends On | RFC 001 |
| Scope | DB-driven cashflow rules, rule consumption behavior, business-level cashflow metrics |

## Executive Summary

RFC 022 modernized cashflow processing by moving rule logic from static code config to database policy records and adding business-level metrics.

Current state is strong but not fully complete:
1. DB-driven `cashflow_rules` and repository/cache loading are implemented.
2. `cashflows_created_total` metric is implemented and emitted with `classification`/`timing` labels.
3. A key agility goal remains incomplete: runtime rule-change refresh without service restart is not implemented (module-level cache has no invalidation/refresh path).

Classification: `Partially implemented (requires enhancement)`.

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
3. Consumer uses module-level cache for fast rule lookup.
4. Missing rule path sends event to DLQ as non-retryable configuration error.
5. `CASHFLOWS_CREATED_TOTAL` counter is defined and incremented in `CashflowLogic.calculate`.
6. Unit tests exist for rules repository, consumer behavior, and metric label emission.

Not yet implemented:
1. No cache refresh or invalidation path for runtime rule updates.
2. No admin endpoint/signal-driven reload workflow in current service.

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
| Load/cached rule lookup in consumer | Implemented (module-level cache) | `transaction_consumer.py` |
| Metric `cashflows_created_total` with labels | Implemented | `monitoring.py`; `cashflow_logic.py`; core tests |
| Dynamic rule updates without restart | Not implemented (cache refresh absent) | `transaction_consumer.py` |

## Design Reasoning and Trade-offs

1. DB-driven rules improve governance and remove business-policy code redeploy dependency.
2. In-memory cache preserves consumer throughput.

Trade-off:
- Current cache strategy optimizes steady-state performance but sacrifices runtime agility until reload mechanism exists.

## Gap Assessment

Primary remaining gap:
1. Introduce safe cache refresh/reload semantics so rule updates are applied without service restart.

Secondary considerations:
1. Add operational visibility for rule-version currently loaded by each consumer instance.
2. Add deterministic test proving hot rule update behavior once implemented.

## Deviations and Evolution Since Original RFC

1. Core architecture completed DB migration and metric instrumentation.
2. Dynamic refresh requirement was deferred implicitly and should now be tracked explicitly as a delta.

## Proposed Changes

1. Add rule-cache refresh mechanism (TTL, admin trigger, or event-driven invalidation).
2. Add test coverage for hot-rule update behavior.
3. Document reload semantics in cashflow operations guide.

## Test and Validation Evidence

1. Repository query behavior tests:
   - `tests/unit/services/calculators/cashflow_calculator_service/unit/repositories/test_cashflow_rules_repository.py`
2. Consumer cache/rule usage tests:
   - `tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
3. Metric emission tests:
   - `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`

## Original Acceptance Criteria Alignment

Partially aligned:
1. Schema and DB-driven configuration: met.
2. Business metric instrumentation: met.
3. Runtime no-restart dynamic update behavior: not yet met.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Preferred reload strategy: event-driven invalidation, periodic TTL reload, or explicit admin endpoint?
2. Should rule updates be versioned and auditable with `effective_from` to avoid mid-batch ambiguity?

## Next Actions

1. Track and implement dynamic rule refresh delta in `RFC-DELTA-BACKLOG.md`.
2. Add regression tests and operations documentation for reload semantics.
