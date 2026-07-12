# CR-020 Cost Engine Ownership Finalization

## Scope

Finalize ownership of the remaining cost-basis engine code after the earlier
dead-surface and model-surface cleanup.

## Findings

After CR-019, the remaining production imports of the engine were all inside
`cost_calculator_service`:

- `app/consumer.py`
- `app/repository.py`
- `app/transaction_processor.py`

No other production service consumed the engine package. All remaining external
references were tests or historical documentation.

That means the engine was no longer a real shared library. Keeping it under
`src/libs` created a false architectural signal.

## Actions taken

- Folded the remaining engine into the owning service under:
  - `src/services/calculators/cost_calculator_service/app/cost_engine/domain/*`
  - `src/services/calculators/cost_calculator_service/app/cost_engine/processing/*`
- Updated service-local imports to use the local engine package.
- Moved the engine unit tests under service ownership:
  - `tests/unit/services/calculators/cost_calculator_service/engine/*`
- Removed the obsolete `src/libs/financial-calculator-engine/` package and its
  packaging/runtime references.
- Updated current-state cost-calculator documentation and test-manifest paths.

## Rationale

Service-private code should live with the service that owns it.

This improves:

- ownership clarity
- deployability
- container/runtime correctness
- package structure meaning
- reviewability of service-local changes

It does not reduce testability. The cost engine remains pure and unit-testable,
but it no longer pretends to be platform-shared code.

## Evidence

- `src/services/calculators/cost_calculator_service/app/cost_engine/domain/*`
- `src/services/calculators/cost_calculator_service/app/cost_engine/processing/*`
- `tests/unit/services/calculators/cost_calculator_service/engine/*`
- `src/services/calculators/cost_calculator_service/Dockerfile`
- `scripts/test_manifest.py`
