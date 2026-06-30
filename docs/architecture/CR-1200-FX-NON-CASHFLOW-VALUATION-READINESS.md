# CR-1200 FX Non-Cashflow Valuation Readiness

Date: 2026-06-30

## Scope

FX contract lifecycle transaction processing across:

- `portfolio_common.transaction_domain.effective_processing_type`
- `cashflow_calculator_service`
- `pipeline_orchestrator_service`

## Finding

The FX lifecycle contract correctly treats `FX_CONTRACT_OPEN` and `FX_CONTRACT_CLOSE` as
position-exposure rows without cashflow rows. Settlement cash movements are represented by separate
FX cash settlement rows.

The pipeline orchestrator still required both cost and cashflow stage signals before publishing
valuation readiness. This could strand FX forward position materialization when the cashflow
consumer intentionally skipped lifecycle rows.

## Action Taken

Promoted the cashflow-required decision into the shared transaction-domain policy:

- `requires_cashflow_processing(event)`
- `NON_CASHFLOW_PROCESSING_TYPES`

The cashflow consumer now uses that shared policy instead of a service-local lifecycle list. The
pipeline orchestrator uses the same policy to mark non-cashflow lifecycle stages cashflow-satisfied
and emits readiness with `readiness_reason="cost_completed_non_cashflow"`.

## Behavior And Compatibility

Public API response contracts are unchanged.

Intentional runtime behavior change:

- `FX_CONTRACT_OPEN` and `FX_CONTRACT_CLOSE` valuation readiness can publish after the processed
  transaction/cost signal without waiting for a cashflow signal.

Preserved behavior:

- standard transaction rows still require both processed and cashflow signals,
- FX cash settlement rows still require cashflow processing,
- emitted stage events retain the existing boolean readiness fields, with the readiness reason
  distinguishing the non-cashflow policy path.

## Evidence

Focused unit proof:

- `python -m pytest tests/unit/libs/portfolio_common/test_effective_processing_type.py tests/unit/services/pipeline_orchestrator_service/services/test_pipeline_orchestrator_service.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py -q`
- Result: `86 passed`

Focused static proof:

- `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/effective_processing_type.py src/libs/portfolio-common/portfolio_common/transaction_domain/__init__.py src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py src/services/pipeline_orchestrator_service/app/services/pipeline_orchestrator_service.py tests/unit/libs/portfolio_common/test_effective_processing_type.py tests/unit/services/pipeline_orchestrator_service/services/test_pipeline_orchestrator_service.py`
- Result: passed

Focused format proof:

- `make quality-ruff-format-gate`
- Result: passed

Architecture proof:

- `python scripts/architecture_boundary_guard.py --strict`
- Result: passed

Local runtime note:

- `make test-e2e-smoke` was attempted, but the local stack failed during fixture setup with HTTP
  500 from `/ingest/portfolios` before the FX lifecycle assertions ran. This is recorded as local
  runtime/bootstrap evidence to diagnose separately, not as proof against the FX readiness fix.

## Reusable Pattern

When a transaction processing subtype changes downstream stage prerequisites, encode that rule in
`portfolio_common.transaction_domain` and have consumers, orchestrators, reconciliation, and
supportability code consume the same policy. Do not duplicate local skip lists in service code.

## Documentation And Wiki Decision

Updated repository context because this is durable repo-local guidance for FX lifecycle and
pipeline readiness.

No wiki source update is required. This is internal processing pipeline behavior and does not change
operator-facing commands, public API shape, or supported-feature claims.

