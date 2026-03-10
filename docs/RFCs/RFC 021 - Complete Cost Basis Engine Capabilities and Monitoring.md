# RFC 021 - Complete Cost Basis Engine Capabilities and Monitoring

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-09-02 |
| Last Updated | 2026-03-04 |
| Owners | `financial-calculator-engine`, `cost_calculator_service`, `portfolio-common`, `persistence_service` |
| Depends On | RFC 005, RFC 010 |
| Scope | AVCO method support, portfolio-level method selection, recalculation observability |

## Executive Summary

RFC 021 targeted feature-completeness and operability for cost basis processing:
1. Add Average Cost (AVCO) support alongside FIFO.
2. Make method configurable at portfolio level.
3. Add specific recalculation depth/duration metrics.

Current lotus-core implementation aligns with these goals and includes test coverage at unit/integration/E2E layers.

## Original Requested Requirements (Preserved)

Original RFC 021 requested:
1. Add `portfolios.cost_basis_method` with FIFO default.
2. Implement `AverageCostBasisStrategy` for dual-currency aware AVCO processing.
3. Select strategy dynamically in cost-calculator consumer.
4. Emit recalculation observability metrics (`recalculation_depth`, `recalculation_duration_seconds`).
5. Add AVCO pipeline validation and documentation updates.

## Current Implementation Reality

Implemented behavior:
1. Schema migration adds `cost_basis_method` with default `FIFO`.
2. Portfolio model/event/DTO paths include method field.
3. Cost-calculator consumer resolves method and instantiates FIFO or AVCO strategy.
4. Financial engine defines and emits both recalculation metrics.
5. AVCO unit and E2E tests are present.
6. Cost-calculator docs include AVCO methodology and ops metrics guidance.

Evidence:
- `alembic/versions/3a9c7b2d1e0f_feat_add_cost_basis_method_to_portfolios.py`
- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `src/libs/portfolio-common/portfolio_common/events.py`
- `src/services/calculators/cost_calculator_service/app/consumer.py`
- `src/libs/financial-calculator-engine/src/logic/cost_basis_strategies.py`
- `src/services/calculators/cost_calculator_service/app/monitoring.py`
- `src/services/calculators/cost_calculator_service/app/transaction_processor.py`
- `tests/unit/libs/financial-calculator-engine/unit/test_cost_basis_strategies.py`
- `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
- `tests/integration/services/persistence_service/repositories/test_repositories.py`
- `tests/e2e/test_avco_workflow.py`
- `docs/features/cost_calculator/01_Feature_Cost_Calculator_Overview.md`
- `docs/features/cost_calculator/03_Methodology_Guide.md`
- `docs/features/cost_calculator/04_Operations_Troubleshooting_Guide.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Portfolio-level cost basis method | Implemented (`cost_basis_method` schema + model + ingestion/event paths) | migration + model/event files |
| AVCO strategy | Implemented in engine logic | `cost_basis_strategies.py`; strategy tests |
| Runtime strategy selection | Implemented in cost calculator consumer | `consumer.py`; consumer tests |
| Recalculation metrics | Implemented and observed in processor | engine monitoring + processor files |
| End-to-end AVCO validation | Implemented | `test_avco_workflow.py` |

## Design Reasoning and Trade-offs

1. Strategy pattern keeps FIFO baseline stable while adding AVCO extensibly.
2. Portfolio-level config supports jurisdiction/client accounting differences.
3. Processor-level metrics isolate core computation cost from transport/storage concerns.

Trade-off:
- Method changes are config-driven but historical full re-cast semantics remain a separate operational concern.

## Gap Assessment

No material implementation gap remains for RFC 021 core intent.

## Deviations and Evolution Since Original RFC

1. SELL policy linkage now also tags AVCO-related policy metadata in transaction-domain enrichment.
2. Follow-on transaction RFC streams (BUY/SELL) use this method field as a shared primitive.

## Proposed Changes

1. Keep RFC 021 classification as `Fully implemented and aligned`.
2. Keep any future "historical recast on method change" behavior as a separate explicit RFC.

## Test and Validation Evidence

1. Engine AVCO correctness tests (including dual currency):
   - `tests/unit/libs/financial-calculator-engine/unit/test_cost_basis_strategies.py`
2. Consumer strategy-selection tests:
   - `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
3. Persistence/model integration for `cost_basis_method`:
   - `tests/integration/services/persistence_service/repositories/test_repositories.py`
4. End-to-end AVCO pipeline proof:
   - `tests/e2e/test_avco_workflow.py`

## Original Acceptance Criteria Alignment

Acceptance criteria are met for schema, strategy logic, selection behavior, metrics, E2E validation, and documentation refresh.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should a future migration path support deterministic historical revaluation when portfolio method changes after prior transactions exist?

## Next Actions

1. Maintain current AVCO/FIFO baseline.
2. Treat historical method-change replay behavior as separate future scope when required.
