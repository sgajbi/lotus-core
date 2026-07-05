# CR-1401 Cost Calculation Event Processor

## Objective

Fix GitHub issue #550 by extracting valid cost-calculation event orchestration out of the Kafka
consumer into an application processor with explicit repository, idempotency, and outbox
dependencies.

## Expected Improvement

- `CostCalculatorConsumer` remains responsible for Kafka message decoding, correlation context,
  retry classification, and DLQ handoff.
- `CostCalculationEventProcessor` owns valid-event workflow sequencing after the transport boundary:
  idempotency claim, portfolio/instrument reads, cost workflow invocation, emitted-event assembly,
  and outbox staging.
- `CostCalculationProcessorDependencies` makes concrete repository/idempotency/outbox dependencies
  visible and fakeable in focused tests.
- The processor can be executed in unit tests without constructing a Kafka consumer object.
- Existing cash-leg validation, Bundle A reconciliation diagnostics, outbox topics, outbox payload
  shape, and lifecycle metrics are preserved through the existing workflow methods.
- The change improves design modularity inside the existing deployable; no runtime service split is
  justified.

## Scope

- Added `cost_calculation_processor.py` with the processor, dependency bundle, dependency factory,
  workflow protocol, and retryable `PortfolioNotFoundError` application error.
- Routed `CostCalculatorConsumer._process_valid_cost_event(...)` through the processor and factory.
- Updated consumer tests to patch the processor factory boundary.
- Added direct processor tests for valid-event orchestration and duplicate idempotency skip without
  a Kafka consumer object.

## Behavior And Compatibility

No Kafka topic, event payload, outbox event type, outbox aggregate metadata, idempotency service
name, cash-leg validation behavior, Bundle A reconciliation evidence shape, retry/DLQ behavior,
database schema, OpenAPI contract, or runtime topology changed.

## Same-Pattern Scan

- `rg "CostCalculatorRepository\\(|IdempotencyRepository\\(|OutboxRepository\\(" src/services/calculators/cost_calculator_service/app tests/unit/services/calculators/cost_calculator_service/consumer`
  shows concrete construction only in `cost_calculation_processor.py` and repository-specific tests.
- The remaining cost-consumer helper methods are now workflow methods invoked by the processor.
  A future deeper slice may move those helpers into a non-consumer workflow class, but the issue's
  repository-construction and valid-event orchestration blocker is cleared in this slice.

## Validation Evidence

- `python -m pytest tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py -q`
  - `36 passed`
- `python -m ruff check src\services\calculators\cost_calculator_service\app\consumer.py src\services\calculators\cost_calculator_service\app\cost_calculation_processor.py tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py`
  - passed

Final architecture/docs/lint/diff checks are recorded in the issue comment before commit.

## Documentation And Guidance Decision

- Repo context updated because future consumers should keep valid-message use-case orchestration
  behind processor/dependency-factory boundaries instead of constructing repositories directly.
- Codebase review ledger updated with this hardened boundary.
- No wiki update: no operator command, endpoint contract, deployment flow, or runbook truth changed.
- No platform skill update: current backend delivery and codebase-review guidance already requires
  ports/factories and same-pattern scans for repeated concrete infrastructure coupling.
