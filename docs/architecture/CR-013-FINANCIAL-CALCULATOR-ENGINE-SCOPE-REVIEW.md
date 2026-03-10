# CR-013 Financial Calculator Engine Scope Review

## Scope

Review the purpose of `src/libs/financial-calculator-engine` and determine whether any part of it should be folded into the service that actually owns it.

Reviewed areas:

- `src/libs/financial-calculator-engine/src/core/*`
- `src/libs/financial-calculator-engine/src/logic/*`
- `src/libs/financial-calculator-engine/src/engine/*`
- `src/services/calculators/cost_calculator_service/app/consumer.py`
- direct tests and docs referring to the engine layer

## Findings

### 1. The library is real, but its scope is narrower than its name

The package is not dead code. It is used in production by `cost_calculator_service`.

Live usage included:

- parser
- sorter
- disposition engine
- cost calculator
- engine transaction processor

However, only the `cost_calculator_service` owned the `engine/` layer. No other service used:

- `engine.transaction_processor`
- `engine.monitoring`

So the broad package name overstated what was actually shared.

### 2. `core/` and `logic/` are still valid shared domain-engine layers

The reusable value remains in:

- transaction models/enums
- parsing
- sorting
- lot-disposition logic
- cost-basis strategies
- cost calculation rules

Those stay appropriately separated from Kafka and database concerns.

### 3. The `engine/` layer was service-owned orchestration, not shared engine logic

`TransactionProcessor` is orchestration around the shared domain logic. It belongs with the
service that builds and runs it: `cost_calculator_service`.

Likewise, the recalculation Prometheus metrics are tied to the service-owned recalculation path,
not to a multi-service shared engine.

## Action taken

Implemented in the review program:

- moved `TransactionProcessor` into:
  - `src/services/calculators/cost_calculator_service/app/transaction_processor.py`
- moved recalculation metrics into:
  - `src/services/calculators/cost_calculator_service/app/monitoring.py`
- updated `cost_calculator_service/app/consumer.py` to import the local transaction processor
- moved the transaction-processor unit test into the cost-calculator service test area
- updated direct manifest/doc references to the new ownership path
- removed the dead `financial-calculator-engine/src/engine/` package

## Sign-off state

Current state: `Hardened`

Reason:

- the shared library now contains only the genuinely reusable cost-basis domain logic
- service-owned orchestration is now owned by the service that runs it
- naming and ownership now better match reality without inlining the whole domain engine into the service
